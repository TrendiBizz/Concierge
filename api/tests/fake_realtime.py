"""A small fake of the OpenAI Realtime and Gemini Live phone protocols, for harness self-tests.

It is NOT a model of either service's quality: it detects speech by loudness, then answers from a
script chosen by how long the caller spoke (long utterance = "explain in detail" -> a long answer,
longest = a lead with a tool call, otherwise a short reply). That is enough to prove the harness
measures reply latency, barge-in cutoff and tool calls correctly, with no network and no cost.
"""
from __future__ import annotations

import asyncio
import base64
import json
import struct

import websockets

from app import voice_openai

RESPONSE_DELAY = {'openai': 0.25, 'gemini': 0.45}
QUIET_AFTER_SPEECH = 0.3  # seconds of quiet that end a caller turn
LONG_ANSWER_SECONDS = 8.0
SHORT_ANSWER_SECONDS = 0.8


class Session:
    def __init__(self, ws, kind):
        self.ws, self.kind = ws, kind
        self.stream: asyncio.Task | None = None
        self.speech_started_at = None
        self.last_loud = None
        self.speech_seconds = 0.0
        self.counter = 0
        self.calls_seen: list[dict] = []

    async def send(self, event):
        await self.ws.send(json.dumps(event))

    # --- audio out ---
    async def stream_audio(self, seconds, text):
        self.counter += 1
        item = f'item{self.counter}'
        await asyncio.sleep(RESPONSE_DELAY[self.kind])
        chunks = int(seconds / 0.02)
        for _ in range(chunks):
            if self.kind == 'openai':
                pcm = struct.pack('<160h', *([4000] * 80 + [-4000] * 80))
                await self.send({'type': 'response.output_audio.delta', 'item_id': item,
                                 'delta': base64.b64encode(voice_openai.pcm16_to_ulaw(pcm)).decode()})
            else:
                pcm = struct.pack('<480h', *([4000] * 240 + [-4000] * 240))
                await self.send({'serverContent': {'modelTurn': {'parts': [
                    {'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': base64.b64encode(pcm).decode()}}]}}})
            await asyncio.sleep(0.02)
        if self.kind == 'openai':
            await self.send({'type': 'response.output_audio_transcript.done', 'item_id': item, 'transcript': text})
            await self.send({'type': 'response.done'})
        else:
            await self.send({'serverContent': {'outputTranscription': {'text': text, 'finished': True}}})
            await self.send({'serverContent': {'turnComplete': True}})

    def speak(self, seconds, text):
        self.stream = asyncio.create_task(self.stream_audio(seconds, text))

    async def tool_call(self):
        self.counter += 1
        args = {'name': 'Sam Taylor', 'phone': '021 555 0100'}
        if self.kind == 'openai':
            await self.send({'type': 'response.function_call_arguments.done', 'call_id': f'call{self.counter}',
                             'name': 'capture_lead', 'arguments': json.dumps(args)})
            await self.send({'type': 'response.done'})
        else:
            await self.send({'toolCall': {'functionCalls': [
                {'id': f'call{self.counter}', 'name': 'capture_lead', 'args': args}]}})

    # --- caller audio in ---
    async def on_audio(self, pcm, loop_time):
        loud = sum(abs(s) for s in struct.unpack(f'<{len(pcm) // 2}h', pcm)) / max(1, len(pcm) // 2) > 500
        if loud:
            self.last_loud = loop_time
            if self.speech_started_at is None:
                self.speech_started_at = loop_time
                self.speech_seconds = 0.0
                if self.stream and not self.stream.done():
                    self.stream.cancel()
                    if self.kind == 'gemini':
                        await self.send({'serverContent': {'interrupted': True}})
                if self.kind == 'openai':
                    await self.send({'type': 'input_audio_buffer.speech_started'})
            self.speech_seconds += len(pcm) / (32000 if self.kind == 'gemini' else 16000)
        elif self.speech_started_at is not None and loop_time - self.last_loud >= QUIET_AFTER_SPEECH:
            seconds = self.speech_seconds
            self.speech_started_at = None
            if self.kind == 'openai':
                await self.send({'type': 'input_audio_buffer.speech_stopped'})
            await self.respond(seconds)

    async def respond(self, caller_seconds):
        if caller_seconds >= 3.0:
            await self.tool_call()
        elif caller_seconds >= 2.0:
            self.speak(LONG_ANSWER_SECONDS, 'Here is a long step by step explanation of how it works.')
        else:
            self.speak(SHORT_ANSWER_SECONDS, 'We are open nine to five on weekdays.')


async def handler(ws):
    kind = 'openai' if ws.request.path.startswith('/openai') else 'gemini'
    session = Session(ws, kind)
    loop = asyncio.get_running_loop()
    try:
        async for message in ws:
            event = json.loads(message)
            if kind == 'openai':
                t = event.get('type')
                if t == 'session.update':
                    await session.send({'type': 'session.created'})
                    await session.send({'type': 'session.updated'})
                elif t == 'response.create':
                    session.speak(1.0, 'Hello, Test Plumbing, how can I help?')
                elif t == 'input_audio_buffer.append':
                    pcm = voice_openai.ulaw_to_pcm16(base64.b64decode(event['audio']))
                    await session.on_audio(pcm, loop.time())
                elif t == 'conversation.item.create' and event['item'].get('type') == 'function_call_output':
                    session.speak(SHORT_ANSWER_SECONDS, 'Thanks Sam, we will call you back. Goodbye.')
            else:
                if 'setup' in event:
                    await session.send({'setupComplete': {}})
                elif 'clientContent' in event:
                    session.speak(1.0, 'Hello, Test Plumbing, how can I help?')
                elif 'realtimeInput' in event:
                    data = base64.b64decode(event['realtimeInput']['audio']['data'])
                    await session.on_audio(data, loop.time())
                elif 'toolResponse' in event:
                    session.speak(SHORT_ANSWER_SECONDS, 'Thanks Sam, we will call you back. Goodbye.')
    except websockets.ConnectionClosed:
        pass
    finally:
        if session.stream and not session.stream.done():
            session.stream.cancel()


class FakeRealtimeServer:
    async def __aenter__(self):
        self.server = await websockets.serve(handler, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()

    def url(self, provider):
        name = 'openai' if provider == 'openai_realtime' else 'gemini'
        return f'ws://127.0.0.1:{self.port}/{name}'
