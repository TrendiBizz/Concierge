"""Private Asterisk AudioSocket → realtime voice bridge (Google Gemini 3.8 Live or OpenAI Realtime).

The provider is chosen by PHONE_VOICE_PROVIDER (gemini_live, the default, or openai_realtime).

One listener per provisioned business: the caller/model never chooses a tenant.
Run separately from HTTP workers: python -m app.asterisk_bridge.
AudioSocket is unencrypted: bind loopback or an isolated private container network.
"""
from array import array
import asyncio
import base64
from dataclasses import dataclass
import ipaddress
import json
import logging
import os
import re
import secrets
import struct
import sys
import uuid

import websockets

from . import (asterisk_ami, call_control, channel_authorization, convo, db, enquiries, enquiry_alerts, events, tenants, voice,
               voice_openai, voice_records)
from .config import get_settings, phone_voice_ready
from .rag import build_system_prompt
from .tools import run_tool
from .telephone_recording import TelephoneRecording

log = logging.getLogger('concierge.asterisk')
FRAME_BYTES = 320  # 20ms PCM16 LE mono at 8kHz, native AudioSocket application format
MAX_SECONDS = 600
# Silent monitoring changes what a caller must be told, so the greeting discloses it *when the
# capability exists* -- not speculatively, and not only in a policy document.
LIVE_LISTEN_DISCLOSURE = (
    ' This line is answered by an automated assistant, and a member of our team may listen to the '
    'call while it happens or join it. Say so in your greeting, in your own words.')
MAX_ERRORS = 5
# Telephone pacing needs a longer end-of-turn silence than the browser: a caller
# dictating a phone number or email address pauses mid-sentence.
SILENCE_DURATION_MS = 700
# Automatic activity detection normally answers a caller turn on its own. If a
# cancelled or lost response leaves the caller in silence, ask the model once.
REPLY_NUDGE_SECONDS = 5.0
GEMINI_VOICES = frozenset({
    'Aoede', 'Charon', 'Fenrir', 'Kore', 'Puck', 'Leda', 'Orus', 'Zephyr',
})


from .speech_text import clean_speech


# Say a number once. The test call of 2026-11-13 read the caller's number three times: the lead step,
# the text-copy step and the confirmation each told the model to read it back. A caller who then
# interrupts a read-back must not trigger a fresh one.
READBACK_RULES = (
    ' Say any phone number or email address back at most once on the whole call, in short groups, '
    'then carry on. After that, call it "that number" or "the same number" and never recite it again; '
    'these rules override any tool instruction to read back again. If the caller interrupts while you '
    'are reading something back, stop at once, treat what they said as the answer, and do not start '
    'the read-back over. If they correct a number, read only the corrected number, once. '
    'Never mention devices, queues, delivery systems or limits to the caller; say the team will follow up.')
SMS_OFFLINE_RULE = (
    ' Text messages cannot be sent right now. Do not offer a text copy or a recording link by SMS and '
    'do not promise any text. Offer a callback, or an email copy if the caller gives an email address.')


def upsample_8k_to_16k(pcm: bytes) -> bytes:
    """Upsample 8kHz PCM16 LE mono to 16kHz PCM16 LE mono via 2x linear interpolation."""
    if len(pcm) % 2:
        raise ValueError('Invalid PCM16 frame')
    if not pcm:
        return b''
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    n = len(samples)
    out = array('h', [0]) * (n * 2)
    for i in range(n - 1):
        s0 = samples[i]
        out[2 * i] = s0
        out[2 * i + 1] = (s0 + samples[i + 1]) >> 1
    last = samples[n - 1]
    out[2 * n - 2] = last
    out[2 * n - 1] = last
    if sys.byteorder != 'little':
        out.byteswap()
    return out.tobytes()


def downsample_24k_to_8k(pcm: bytes) -> bytes:
    """Downsample 24kHz PCM16 LE mono to 8kHz PCM16 LE mono via 3:1 boxcar averaging."""
    if len(pcm) % 2:
        raise ValueError('Invalid PCM16 frame')
    usable = (len(pcm) // 6) * 6
    if not usable:
        return b''
    samples = array('h')
    samples.frombytes(pcm[:usable])
    if sys.byteorder != 'little':
        samples.byteswap()
    count = len(samples) // 3
    out = array('h', [0]) * count
    for i in range(count):
        base = i * 3
        out[i] = int((samples[base] + samples[base + 1] + samples[base + 2]) / 3)
    if sys.byteorder != 'little':
        out.byteswap()
    return out.tobytes()


def strip_additional_properties(schema):
    """Recursively strip 'additionalProperties' keys that Gemini Live rejects."""
    if isinstance(schema, dict):
        return {
            k: strip_additional_properties(v)
            for k, v in schema.items()
            if k != 'additionalProperties'
        }
    if isinstance(schema, list):
        return [strip_additional_properties(item) for item in schema]
    return schema


def _gemini_function_declarations(tools) -> list[dict]:
    declarations = []
    for tool in tools or ():
        if not isinstance(tool, dict) or not tool.get('name'):
            continue
        decl = {
            'name': tool['name'],
            'description': tool.get('description', ''),
        }
        params = strip_additional_properties(tool.get('parameters'))
        if isinstance(params, dict) and params.get('properties'):
            decl['parameters'] = params
        declarations.append(decl)
    return declarations


async def sms_copy_available(tenant_id) -> bool:
    """True when the business's SMS phone has checked in recently enough to send a text copy.

    A check that fails is treated as available, so a database hiccup never changes what callers hear.
    """
    try:
        return bool(await db.pool().fetchval(
            'SELECT 1 FROM sms_devices WHERE tenant_id=$1 AND enabled AND last_seen > now() - interval \'2 hours\' LIMIT 1',
            tenant_id))
    except Exception:  # noqa: BLE001
        log.exception('could not check the SMS device; assuming it is available')
        return True


QUICK_QUESTIONS = (
    'After the greeting, ask only what is needed to help, one short question at a time and under ten '
    'words each: what they need, their name, and the best number to call back (or an email if they '
    'prefer). Skip anything they have already told you and never ask for the same thing twice. '
    'Acknowledge in a word or two ("Got it."), never in a sentence. Do not offer a text copy, a '
    'recording link or any other extra unless the caller asks. If the caller asks to be contacted by '
    'email or text, save that as their contact preference with the number or address; that is a callback '
    'preference, not a copy of the conversation. If they do ask for a copy of the conversation, capture '
    'their contact, get one clear yes to the format and destination (say "the same number" if you already '
    'have it), then request_conversation_copy. Never claim a text was sent without a confirmed result. '
    'Once you have what they need, their name and how to reach them, say goodbye in one short sentence '
    'and call end_call. Do not end with an open question.')


def phone_instructions(name: str, *, recording_ok: bool, listen_in: bool, sms_ok: bool,
                       consent_mode: str = 'opt_out') -> str:
    """The telephone receptionist's instructions after the shared business prompt.

    The opening is two short sentences. "Recorded" is only ever said when recording will really happen
    (the business authorised it and the platform has it switched on); otherwise the notice says
    "transcribed", which is always true. Listen-in is added only while a human really can listen in.
    In `strict_opt_in` mode (AU all-party consent states), recording stays OFF until the caller
    explicitly says yes.
    """
    business = (name or 'the business').replace('"', '').strip() or 'the business'
    listen = ' and a team member may listen in' if listen_in else ''
    if recording_ok and consent_mode == 'strict_opt_in':
        text = (
            "\nYou are this business's automated receptionist. Open the call with exactly this, warmly and with "
            f'nothing added: "Hello, I\'m the AI assistant for {business}. May I record this call for quality '
            f'and training purposes{listen}?" '
            'Wait for the caller\'s explicit answer before calling set_call_recording. '
            'ONLY call set_call_recording with enabled=true and confirmed=true if they explicitly say yes. '
            'If they decline, hesitate, or do not clearly agree, call set_call_recording with enabled=false '
            'and confirmed=false, say "No problem, this call will not be recorded," and carry on. ')
        return text + QUICK_QUESTIONS + READBACK_RULES + ('' if sms_ok else SMS_OFFLINE_RULE)
    verb = 'recorded' if recording_ok else 'transcribed'
    text = (
        "\nYou are this business's automated receptionist. Open the call with exactly this, warmly and with "
        f'nothing added: "Hello, I\'m the AI assistant for {business}. Our calls are {verb} for quality and '
        f'training purposes{listen}." ')
    if recording_ok:
        text += (
            'Right after saying it, call set_call_recording with enabled=true and confirmed=true: the caller '
            'has been told. If they object to recording or ask you to stop, call set_call_recording with '
            'enabled=false at once (it discards the audio), say "No problem" and carry on. ')
    else:
        text += 'Audio is not recorded on this line; never say or imply that it is. '
    return text + QUICK_QUESTIONS + READBACK_RULES + ('' if sms_ok else SMS_OFFLINE_RULE)


@dataclass(frozen=True)
class Route:
    tenant: str
    number: str
    port: int


def greeting_disclosure(media_control: bool) -> str:
    """The extra greeting sentence owed to callers when a human may listen in."""
    return LIVE_LISTEN_DISCLOSURE if media_control else ''


def routes_from_json(value):
    rows = json.loads(value)
    if not isinstance(rows, list) or not rows:
        raise ValueError('At least one explicit business route is required')
    routes = [Route(**r) for r in rows]
    if len({r.port for r in routes}) != len(routes):
        raise ValueError('Each business route needs a unique private port')
    if len({r.number for r in routes}) != len(routes):
        raise ValueError('Ambiguous forwarding destinations are forbidden')
    for r in routes:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', r.tenant):
            raise ValueError('Invalid business slug')
        if not re.fullmatch(r'\+[1-9]\d{6,14}', r.number) or not 1024 <= r.port <= 65535:
            raise ValueError('Invalid destination or listener port')
    return routes


async def packet(reader):
    kind, length = struct.unpack('!BH', await reader.readexactly(3))
    if length > 8192:
        raise ValueError('Oversized AudioSocket packet')
    return kind, await reader.readexactly(length)


async def send_packet(writer, kind, body=b''):
    writer.write(struct.pack('!BH', kind, len(body)) + body)
    await writer.drain()


class MediaBridge:
    """Bidirectional audio bridge between Asterisk AudioSocket (8kHz) and Gemini Live (16kHz in / 24kHz out)."""
    def __init__(self, reader, writer, ws, session, on_transcript, on_tool, recording=None,
                 reply_nudge=REPLY_NUDGE_SECONDS, provider='gemini_live'):
        self.provider = provider
        # OpenAI Realtime state: the assistant item being spoken, how many 8 kHz PCM16 bytes of it
        # we queued (to tell the model how much the caller actually heard), partial transcripts,
        # and whether tool results are waiting for a follow-up response.
        self._oa_item = None
        self._oa_bytes = 0
        self._oa_text = {}
        self._oa_user_waiting = False
        self._oa_deferred = []
        self._oa_tools_pending = False
        self.recording = recording
        self.reader, self.writer, self.ws = reader, writer, ws
        self.session = session or {}
        self.on_transcript, self.on_tool = on_transcript, on_tool
        self.playback = bytearray()
        self._pcm24_rem = b''
        self.ready = asyncio.Event()
        self.seen_transcripts, self.seen_tools = {}, set()
        self.ending = False
        self.speaking = False
        self.reply_nudge = reply_nudge
        self.caller_speaking = False
        self.errors = 0
        self.reply_pending = False
        self.reply_since = 0.0
        self._user_turn = 1
        self._user_text = ''
        self._assistant_turn = 1
        self._assistant_text = ''

    def _setup_payload(self) -> dict:
        cfg = get_settings()
        requested_voice = self.session.get('gemini_voice') or self.session.get('voice')
        voice_name = requested_voice if requested_voice in GEMINI_VOICES else cfg.gemini_live_voice
        generation_config = {
            'responseModalities': ['AUDIO'],
            'speechConfig': {
                'voiceConfig': {
                    'prebuiltVoiceConfig': {'voiceName': voice_name},
                },
            },
        }
        thinking_level = self.session.get('thinking_level') or cfg.gemini_thinking_level
        if thinking_level:
            generation_config['thinkingConfig'] = {'thinkingLevel': thinking_level}

        setup = {
            'model': self.session.get('model') or cfg.gemini_live_model,
            'generationConfig': generation_config,
            'realtimeInputConfig': {
                'automaticActivityDetection': {
                    'prefixPaddingMs': 300,
                    'silenceDurationMs': SILENCE_DURATION_MS,
                },
                'activityHandling': 'START_OF_ACTIVITY_INTERRUPTS',
            },
            'inputAudioTranscription': {},
            'outputAudioTranscription': {},
            'contextWindowCompression': {
                'slidingWindow': {},
            },
        }
        instructions = self.session.get('instructions')
        if instructions:
            setup['systemInstruction'] = {'parts': [{'text': instructions}]}
        declarations = _gemini_function_declarations(self.session.get('tools'))
        if declarations:
            setup['tools'] = [{'functionDeclarations': declarations}]
        return {'setup': setup}

    async def _emit_transcript(self, role: str, item_id: str, text: str) -> None:
        if not text or not text.strip():
            return
        identity = (item_id, role)
        if self.seen_transcripts.get(identity) == text:
            return
        self.seen_transcripts[identity] = text
        if self.on_transcript is not None:
            await self.on_transcript(role, text[:10000], item_id)

    def _finish_user_turn(self) -> None:
        if self._user_text:
            self._user_turn += 1
            self._user_text = ''

    def _finish_assistant_turn(self) -> None:
        if self._assistant_text:
            self._assistant_turn += 1
            self._assistant_text = ''

    async def input(self):
        await asyncio.wait_for(self.ready.wait(), 15)
        reading = asyncio.create_task(packet(self.reader))
        try:
            while True:
                # Wait()/silent endpoints may send no frames. Gemini VAD still needs
                # real-time silence to finish the caller's turn. Shield the packet
                # read: cancelling readexactly can lose half a frame.
                done, _ = await asyncio.wait((reading,), timeout=.02)
                if done:
                    kind, body = reading.result()
                    if kind == 0:
                        return
                    if kind == 0x10:
                        if not body or len(body) % 2:
                            raise ValueError('Invalid PCM16 frame')
                    elif kind == 3 and len(body) == 1:
                        reading = asyncio.create_task(packet(self.reader))
                        continue
                    else:
                        raise ValueError('Unexpected AudioSocket frame')
                    reading = asyncio.create_task(packet(self.reader))
                else:
                    body = b'\0' * FRAME_BYTES
                if self.recording:
                    self.recording.append(body)
                if self.provider == 'openai_realtime':
                    await self.ws.send(json.dumps({
                        'type': 'input_audio_buffer.append',
                        'audio': base64.b64encode(voice_openai.pcm16_to_ulaw(body)).decode(),
                    }))
                    continue
                pcm16 = upsample_8k_to_16k(body)
                await self.ws.send(json.dumps({
                    'realtimeInput': {
                        'audio': {
                            'data': base64.b64encode(pcm16).decode(),
                            'mimeType': 'audio/pcm;rate=16000',
                        }
                    }
                }))
        finally:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)

    async def output(self):
        idle_since = None
        while True:
            started = asyncio.get_running_loop().time()
            if self.playback:
                body = bytes(self.playback[:FRAME_BYTES])
                del self.playback[:FRAME_BYTES]
                played = body.ljust(FRAME_BYTES, b'\0')
                await send_packet(self.writer, 0x10, played)
                if self.recording:
                    self.recording.append(played)
                idle_since = None
            elif self.ending and not self.speaking:
                idle_since = idle_since or started
                if started - idle_since >= .4:
                    return
            await asyncio.sleep(max(0, .02 - (asyncio.get_running_loop().time() - started)))

    async def gemini(self):
        await self.ws.send(json.dumps(self._setup_payload()))
        async for message in self.ws:
            event = json.loads(message)
            if 'setupComplete' in event:
                if not self.ready.is_set():
                    self.ready.set()
                    await self.ws.send(json.dumps({
                        'clientContent': {
                            'turns': [{
                                'role': 'user',
                                'parts': [{'text': 'A caller has just connected. Greet them now.'}],
                            }],
                            'turnComplete': True,
                        }
                    }))
                continue

            if 'error' in event:
                error = event.get('error') if isinstance(event.get('error'), dict) else {}
                detail = str(error.get('message') or event.get('message') or event.get('error') or '')[:500]
                code = str(error.get('code') or error.get('status') or 'unknown')
                self.errors += 1
                log.warning('Gemini Live telephone session error %s/%s: %s', code, self.errors, detail)
                if self.errors >= MAX_ERRORS:
                    raise RuntimeError(f'Gemini Live telephone session failed {self.errors} times: {code} {detail}')
                if self.reply_pending:
                    self.reply_since = asyncio.get_running_loop().time()
                continue

            if 'goAway' in event:
                info = event.get('goAway') if isinstance(event.get('goAway'), dict) else {}
                log.warning('Gemini Live session goAway received (timeLeft=%s)', info.get('timeLeft'))
                continue

            if 'serverContent' in event:
                sc = event.get('serverContent') or {}
                if sc.get('interrupted'):
                    self.playback.clear()
                    self._pcm24_rem = b''
                    self.speaking = False
                    self.ending = False
                    self._finish_assistant_turn()

                in_tx = sc.get('inputTranscription')
                if isinstance(in_tx, dict):
                    chunk = in_tx.get('text')
                    if isinstance(chunk, str) and chunk:
                        self._finish_assistant_turn()
                        self._user_text += chunk
                        self.reply_pending = True
                        self.reply_since = asyncio.get_running_loop().time()
                        await self._emit_transcript('user', f'user-{self._user_turn}', self._user_text)
                    if in_tx.get('finished'):
                        self._finish_user_turn()

                model_turn = sc.get('modelTurn')
                if isinstance(model_turn, dict):
                    for part in model_turn.get('parts') or ():
                        if not isinstance(part, dict):
                            continue
                        inline = part.get('inlineData')
                        if isinstance(inline, dict) and inline.get('data'):
                            audio24 = base64.b64decode(inline['data'], validate=True)
                            if len(audio24) % 2:
                                raise ValueError('Invalid Gemini audio frame')
                            buf = self._pcm24_rem + audio24
                            usable = (len(buf) // 6) * 6
                            self._pcm24_rem = buf[usable:]
                            audio8 = downsample_24k_to_8k(buf[:usable]) if usable else b''
                            if len(self.playback) + len(audio8) > 16000 * 30:
                                raise ValueError('Invalid or excessive Gemini audio')
                            if audio8:
                                self.playback.extend(audio8)
                            self._finish_user_turn()
                            self.speaking = True
                            self.reply_pending = False

                out_tx = sc.get('outputTranscription')
                if isinstance(out_tx, dict):
                    chunk = out_tx.get('text')
                    if isinstance(chunk, str) and chunk:
                        self._finish_user_turn()
                        self._assistant_text += chunk
                        self.reply_pending = False
                        await self._emit_transcript('assistant', f'assistant-{self._assistant_turn}', self._assistant_text)
                    if out_tx.get('finished'):
                        self._finish_assistant_turn()

                if sc.get('turnComplete'):
                    self.speaking = False
                    self._finish_assistant_turn()
                    if self.reply_pending:
                        self.reply_since = asyncio.get_running_loop().time()

            if 'toolCallCancellation' in event:
                cancel_ids = (event.get('toolCallCancellation') or {}).get('ids') or ()
                for cid in cancel_ids:
                    if isinstance(cid, str) and cid:
                        self.seen_tools.add(cid)

            if 'toolCall' in event:
                calls = (event.get('toolCall') or {}).get('functionCalls') or ()
                responses = []
                for fc in calls:
                    if not isinstance(fc, dict):
                        continue
                    ident = fc.get('id')
                    if not isinstance(ident, str) or not ident or len(ident) > 200 or ident in self.seen_tools:
                        continue
                    if len(self.seen_tools) >= 40:
                        raise ValueError('Tool limit')
                    self.seen_tools.add(ident)
                    name = fc.get('name', '')
                    args = fc.get('args')
                    if args is None:
                        args = {}
                    elif isinstance(args, str):
                        args = json.loads(args)
                    if not isinstance(args, dict):
                        raise ValueError('Invalid tool arguments')
                    if name == 'end_call':
                        self.ending = True
                        self.speaking = False
                        result = {'ok': True, 'ending': True}
                    else:
                        result = await self.on_tool(name, args)
                    responses.append({'id': ident, 'name': name, 'response': result})
                if responses and not self.ending:
                    await self.ws.send(json.dumps({
                        'toolResponse': {'functionResponses': responses},
                    }, default=str))

    def _oa_setup_payload(self) -> dict:
        cfg = get_settings()
        voice_name = self.session.get('openai_voice') or cfg.openai_realtime_voice
        return voice_openai.session_update(
            model=self.session.get('openai_model') or cfg.openai_realtime_model,
            voice=voice_name, instructions=self.session.get('instructions') or '',
            tools=self.session.get('tools'), transcribe_model=cfg.openai_realtime_transcribe_model,
            turn=cfg.openai_turn_detection)

    async def _oa_send(self, event: dict) -> None:
        await self.ws.send(json.dumps(event, default=str))

    async def _oa_flush_assistant(self, item_id=None) -> None:
        """Emit assistant transcripts, but only after the caller line they answer is saved.

        OpenAI transcribes caller speech asynchronously, so the caller line can arrive after the
        assistant has started replying. Emitting in arrival order would store the turns back to front.
        """
        if self._oa_user_waiting:
            if item_id and item_id not in self._oa_deferred:
                self._oa_deferred.append(item_id)
            return
        pending = [item_id] if item_id else []
        pending = list(dict.fromkeys(self._oa_deferred + pending))
        self._oa_deferred = []
        for ident in pending:
            await self._emit_transcript('assistant', f'assistant-{ident}', self._oa_text.get(ident, ''))

    async def _oa_interrupt(self) -> None:
        """The caller started talking: drop queued audio and tell the model what was really heard."""
        item, played_ms = self._oa_item, 0
        if item and self._oa_bytes:
            played_ms = max(0, (self._oa_bytes - len(self.playback)) // voice_openai.PCM16_8K_BYTES_PER_MS)
        had_audio = bool(self.playback) or self.speaking
        self.playback.clear()
        self.speaking = False
        if had_audio:
            self.ending = False
        if item and had_audio:
            await self._oa_send({'type': 'conversation.item.truncate', 'item_id': item,
                                 'content_index': 0, 'audio_end_ms': int(played_ms)})
            await self._oa_flush_assistant(item)
        self._oa_item, self._oa_bytes = None, 0

    async def openai(self):
        """Run one OpenAI Realtime session: protocol events in, playback and tool results out."""
        await self._oa_send(self._oa_setup_payload())
        loop = asyncio.get_running_loop()
        async for message in self.ws:
            event = json.loads(message)
            kind = event.get('type') or ''

            if kind == 'session.updated':
                if not self.ready.is_set():
                    self.ready.set()
                    for item in voice_openai.user_text_items('A caller has just connected. Greet them now.'):
                        await self._oa_send(item)
                continue

            if kind == 'error':
                if voice_openai.is_benign_error(event):
                    log.debug('OpenAI Realtime housekeeping error ignored: %s', str(event)[:300])
                    continue
                error = event.get('error') if isinstance(event.get('error'), dict) else {}
                detail = str(error.get('message') or '')[:500]
                code = str(error.get('code') or error.get('type') or 'unknown')
                self.errors += 1
                log.warning('OpenAI Realtime telephone session error %s/%s: %s', code, self.errors, detail)
                if self.errors >= MAX_ERRORS:
                    raise RuntimeError(f'OpenAI Realtime telephone session failed {self.errors} times: {code} {detail}')
                if self.reply_pending:
                    self.reply_since = loop.time()
                continue

            if kind == 'input_audio_buffer.speech_started':
                self.caller_speaking = True
                self._oa_user_waiting = True
                await self._oa_interrupt()
                continue

            if kind == 'input_audio_buffer.speech_stopped':
                self.caller_speaking = False
                continue

            if kind == 'conversation.item.input_audio_transcription.completed':
                text = event.get('transcript')
                self._oa_user_waiting = False
                if isinstance(text, str) and text.strip():
                    self.reply_pending = True
                    self.reply_since = loop.time()
                    await self._emit_transcript('user', f"user-{event.get('item_id') or self._user_turn}", text.strip())
                await self._oa_flush_assistant()
                continue

            if kind in ('response.output_audio.delta', 'response.audio.delta'):
                delta = event.get('delta')
                if not isinstance(delta, str) or not delta:
                    continue
                audio8 = voice_openai.ulaw_to_pcm16(base64.b64decode(delta, validate=True))
                if len(self.playback) + len(audio8) > 16000 * 30:
                    raise ValueError('Invalid or excessive OpenAI audio')
                if event.get('item_id') != self._oa_item:
                    self._oa_item, self._oa_bytes = event.get('item_id'), 0
                self.playback.extend(audio8)
                self._oa_bytes += len(audio8)
                self.speaking = True
                self.reply_pending = False
                continue

            if kind in ('response.output_audio_transcript.delta', 'response.audio_transcript.delta'):
                ident = event.get('item_id') or f'a{self._assistant_turn}'
                chunk = event.get('delta')
                if isinstance(chunk, str) and chunk:
                    self._oa_text[ident] = self._oa_text.get(ident, '') + chunk
                continue

            if kind in ('response.output_audio_transcript.done', 'response.audio_transcript.done'):
                ident = event.get('item_id') or f'a{self._assistant_turn}'
                if isinstance(event.get('transcript'), str) and event['transcript']:
                    self._oa_text[ident] = event['transcript']
                await self._oa_flush_assistant(ident)
                continue

            if kind == 'response.function_call_arguments.done':
                ident = event.get('call_id')
                if not isinstance(ident, str) or not ident or len(ident) > 200 or ident in self.seen_tools:
                    continue
                if len(self.seen_tools) >= 40:
                    raise ValueError('Tool limit')
                self.seen_tools.add(ident)
                name = event.get('name', '')
                args = event.get('arguments')
                if args in (None, ''):
                    args = {}
                elif isinstance(args, str):
                    args = json.loads(args)
                if not isinstance(args, dict):
                    raise ValueError('Invalid tool arguments')
                if name == 'end_call':
                    self.ending = True
                    continue
                result = await self.on_tool(name, args)
                await self._oa_send({'type': 'conversation.item.create', 'item': {
                    'type': 'function_call_output', 'call_id': ident,
                    'output': json.dumps(result, default=str)}})
                self._oa_tools_pending = True
                continue

            if kind == 'response.done':
                self.speaking = False
                # Never hold transcripts back past the end of a response: a caller line that was
                # never transcribed (noise, a cough) must not swallow the assistant's words.
                self._oa_user_waiting = False
                await self._oa_flush_assistant()
                if self._oa_tools_pending and not self.ending:
                    self._oa_tools_pending = False
                    await self._oa_send({'type': 'response.create'})
                if self.reply_pending:
                    self.reply_since = loop.time()
                continue

    async def watchdog(self):
        """Give a caller whose turn went unanswered one nudge, not dead air.

        A lost response or a silently dropped turn leaves the caller in silence.
        Re-asking the model once per turn turns that into an answer; repeated
        nudges could talk over the caller, so the debt is cleared when sent.
        """
        while True:
            await asyncio.sleep(.25)
            if not self.reply_pending or self.speaking or self.caller_speaking or self.ending:
                continue
            if asyncio.get_running_loop().time() - self.reply_since < self.reply_nudge:
                continue
            self.reply_pending = False
            log.warning('Caller turn went unanswered for %.0fs; prompting the model',
                        self.reply_nudge)
            try:
                if self.provider == 'openai_realtime':
                    for item in voice_openai.user_text_items('Please reply to the caller.'):
                        await self.ws.send(json.dumps(item))
                    continue
                await self.ws.send(json.dumps({
                    'clientContent': {
                        'turns': [{
                            'role': 'user',
                            'parts': [{'text': 'Please reply to the caller.'}],
                        }],
                        'turnComplete': True,
                    }
                }))
            except Exception:
                log.exception('Reply nudge could not be sent')
                return

    async def run(self):
        loop_fn = self.openai if self.provider == 'openai_realtime' else self.gemini
        tasks = [asyncio.create_task(f()) for f in (self.input, self.output, loop_fn, self.watchdog)]
        try:
            async with asyncio.timeout(MAX_SECONDS):
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def caller_number(call_id: str) -> str:
    """The caller's number for a bridged call, or "" when Asterisk cannot tell us.

    AudioSocket hands the bridge a call UUID and nothing else -- no CallerID -- so the number has
    to be fetched from Asterisk. This matters because the whole point of a case is to recognise the
    customer next time: a call that leaves no number creates a case nobody can find again.

    Returning "" on any doubt is deliberate. Attaching someone else's number to a customer is worse
    than having no number at all.
    """
    uuid_part = (call_id or "").split(":", 1)[-1]
    if not uuid_part:
        return ""
    settings = get_settings()
    if not (settings.ami_host and settings.ami_user and settings.ami_secret):
        return ""
    try:
        config = asterisk_ami.from_settings(settings)
        for event in await asterisk_ami.channels(config):
            unique = event.get("Uniqueid") or ""
            channel = event.get("Channel") or ""
            if unique == uuid_part or uuid_part in channel:
                number = re.sub(r"[\s\-()]", "", (event.get("CallerIDNum") or "").strip())
                # Asterisk reports whatever the carrier sent: often a national number such as
                # 0215551234, not E.164. Demanding a leading + threw away every real caller ID.
                # Accept the digits and let the usual normaliser apply the business's country code.
                return number if re.fullmatch(r'\+?\d{6,15}', number) else ""
    except Exception:
        log.warning("Could not read caller ID from Asterisk for %s", call_id, exc_info=True)
    return ""


async def register(route, call_id):
    cfg = get_settings()
    if not phone_voice_ready(cfg):
        raise ValueError('Phone receptionist is disabled')
    tenant = await tenants.get_by_slug(route.tenant)
    if not tenant or not tenant['phone_enabled']:
        raise ValueError('Business receptionist is disabled')
    from . import tenant_pause
    if await tenant_pause.is_paused(tenant):
        raise ValueError('Business receptionist is paused')
    if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
        raise ValueError('Business has not enabled telephone answering')
    async with db.pool().acquire() as c:
        async with c.transaction():
            await c.execute('SELECT id FROM tenants WHERE id=$1 FOR UPDATE', tenant['id'])
            if not await c.fetchval('SELECT 1 FROM phone_numbers WHERE tenant_id=$1 AND e164=$2 AND enabled', tenant['id'], route.number):
                raise ValueError('Business route is not activated')
            used = await c.fetchval("SELECT count(*) FROM phone_calls WHERE tenant_id=$1 AND started_at>now()-interval '1 day'", tenant['id'])
            if used >= tenant['phone_daily_limit']:
                raise ValueError('Business call limit reached')
            # UNIQUE call_sid rejects replay, including cross-business reuse.
            await c.execute('INSERT INTO phone_calls(tenant_id,call_sid,session_id,from_number,to_number,status) VALUES($1,$2,$3,$4,$5,$6)',
                            tenant['id'], call_id, call_id, await caller_number(call_id), route.number, 'in_progress')
    return tenant


async def prepare(route, call_id):
    """Create the call records and the Gemini Live session for one route. Shared by the
    Python bridge and the internal voice shell."""
    cfg = get_settings()
    tenant = await register(route, call_id)
    conversation = await convo.get_or_create(tenant, call_id, 'phone', None, None)
    # The number recorded at register() is the caller's; capture against it so the case is the
    # person, not an anonymous call.
    stored = await db.pool().fetchrow(
        'SELECT from_number FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2', tenant['id'], call_id)
    caller = (stored['from_number'] if stored else '') or ''
    await enquiries.capture(tenant, 'phone', call_id, 'Inbound telephone enquiry',
                            conversation_id=conversation, phone=caller)
    capability = await voice_records.start(tenant, call_id, channel='phone')
    record_session = await voice_records.authenticate(capability['id'], capability['token'])
    session = voice.build_session(tenant, website=True)
    session['model'] = cfg.gemini_live_model
    session['gemini_voice'] = cfg.gemini_live_voice
    session['thinking_level'] = cfg.gemini_thinking_level
    session['openai_model'] = cfg.openai_realtime_model
    session['openai_voice'] = cfg.openai_realtime_voice
    sms_ok = await sms_copy_available(tenant['id'])
    recording_ok = bool(cfg.voice_recording_enabled
                        and await channel_authorization.is_authorized(tenant['id'], 'call_recording'))
    session['instructions'] = build_system_prompt(tenant, None, channel='phone') + phone_instructions(
        tenant['name'], recording_ok=recording_ok, listen_in=call_control.enabled(), sms_ok=sms_ok,
        consent_mode=tenant.get('call_recording_consent_mode') or 'opt_out')
    session['tools'].append({'type':'function','name':'end_call','description':'End after saying goodbye.',
                             'parameters':{'type':'object','properties':{},'additionalProperties':False}})
    session['tools'].append({'type':'function','name':'set_call_recording',
        'description':'Start recording once the caller has been told calls are recorded (the greeting does this). Disable to discard audio if they object.',
        'parameters':{'type':'object','properties':{'enabled':{'type':'boolean'},'confirmed':{'type':'boolean'}},
                      'required':['enabled','confirmed'],'additionalProperties':False}})
    return {'tenant': tenant, 'conversation': conversation,
            'record_session': record_session, 'session': session}


async def run_phone_tool(tenant, record_session, conversation, call_id, name, args, recording=None):
    """Authorise and run one telephone tool. The Rust shell passes recording=None:
    it owns the audio buffer and applies the consent result itself."""
    if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
        raise ValueError('Business telephone authorization revoked')
    if name == 'set_call_recording':
        if args.get('enabled') is False:
            if recording is not None:
                recording.discard()
            record_session['recording_consent'] = False
        elif args.get('enabled') is True and args.get('confirmed') is True:
            if not (get_settings().voice_recording_enabled and await channel_authorization.is_authorized(tenant['id'], 'call_recording')):
                return {'ok':False, 'error':'Recording is unavailable; take a text message.'}
            if recording is not None:
                recording.start()
            record_session['recording_consent'] = True
        else:
            return {'ok':False, 'error':'Ask for explicit recording permission first.'}
        await db.pool().execute('UPDATE voice_sessions SET recording_consent=$2 WHERE id=$1', record_session['id'], record_session['recording_consent'])
        return {'ok':True, 'recording':record_session['recording_consent']}
    stored = await db.pool().fetchrow(
        'SELECT from_number FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2', tenant['id'], call_id)
    caller = (stored['from_number'] if stored else '') or None
    return await run_tool(tenant, name, args, {'voice_session':record_session, 'conversation_id':conversation, 'session_id':call_id,
                                              'channel':'phone', 'sender_phone':caller})


async def finish(tenant, call_id, conversation, status, record_session=None, reason=''):
    async with db.pool().acquire() as c:
        async with c.transaction():
            row = await c.fetchrow('SELECT ended_at, from_number FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2 FOR UPDATE', tenant['id'], call_id)
            if not row or row['ended_at']:
                return
            all_turns = await c.fetch("SELECT role,content FROM messages WHERE conversation_id=$1 AND role IN ('user','assistant') ORDER BY id", conversation)
            caller_text = '\n'.join(t for t in (clean_speech(r['content']) for r in all_turns if r['role'] == 'user') if t)
            dialogue = '\n\n'.join(
                ('Caller: ' if r['role'] == 'user' else 'Concierge: ') + (clean_speech(r['content']) if r['role'] == 'user' else r['content'])
                for r in all_turns if (clean_speech(r['content']) if r['role'] == 'user' else r['content']).strip()
            )
            if caller_text:
                lead = await c.fetchrow(
                    "UPDATE leads SET message=CASE WHEN message='' OR message='Inbound telephone enquiry' THEN $3 ELSE message END, "
                    "updated_at=now() WHERE tenant_id=$1 AND conversation_id=$2 RETURNING *",
                    tenant['id'], conversation, caller_text[-1000:],
                )
                tail = ''
                if record_session and record_session.get('recording_consent'):
                    has_recording = await c.fetchval(
                        'SELECT 1 FROM voice_recordings WHERE tenant_id=$1 AND session_id=$2 AND conversation_id=$3',
                        tenant['id'], record_session['id'], conversation)
                    if has_recording:
                        token = secrets.token_urlsafe(32)
                        await c.execute(
                            'INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id) VALUES($1,$2,$3)',
                            voice_records.digest(token), record_session['id'], tenant['id'])
                        tail += '\n\nRecording (private link expires in 24 hours): ' + \
                            get_settings().public_base_url.rstrip('/') + '/api/v1/voice/recordings/shared/' + token
                tail += '\n\nThe complete enquiry is saved in your Concierge CRM.'
                owner = await c.fetchval('SELECT owner_number FROM managed_phone_setups WHERE tenant_id=$1', tenant['id'])
                owner = owner or tenant.get('notify_phone')
                await enquiry_alerts.notify(
                    tenant, 'phone', (dialogue or caller_text)[:24000] + tail, lead_id=lead['id'] if lead else None,
                    conversation_id=conversation, connection=c, finalize=True, owner_phone=owner)
            await c.execute('UPDATE phone_calls SET status=$3,ended_at=now(),failure_reason=$4 WHERE tenant_id=$1 AND call_sid=$2', tenant['id'], call_id, status, reason[:500])
    # Record finalized call transcript on the unified contact timeline and emit call.completed webhook.
    try:
        from . import casetimeline, portability
        caller_num = (row['from_number'] or '') if row else ''
        if caller_text and caller_num:
            ck = casetimeline.case_key_for_tenant(tenant, phone=caller_num)
            if ck:
                await casetimeline.record(
                    tenant['id'], case_key=ck, channel='phone', direction='inbound',
                    source_key=f"call-transcript:{call_id}", body=(dialogue or caller_text)[:4000],
                )
        await portability.emit(tenant['id'], 'call.completed', {
            'call_id': call_id, 'from_number': caller_num, 'status': status,
            'transcript': (dialogue or caller_text)[:4000],
        })
    except Exception:
        pass


def provider_connection(settings, provider=None):
    """The WebSocket connection (an async context manager) to the chosen realtime provider."""
    provider = provider or settings.phone_voice_provider
    if provider == 'openai_realtime':
        url, headers = voice_openai.ws_request(settings)
        return websockets.connect(url, additional_headers=headers, open_timeout=15, max_size=4 * 1024 * 1024)
    return websockets.connect(settings.gemini_ws_url, open_timeout=15, max_size=4 * 1024 * 1024)


async def handle(reader, writer, route, networks):
    tenant = conversation = call_id = record_session = None
    recording = TelephoneRecording()
    status = 'failed'
    reason = ''
    try:
        peer = ipaddress.ip_address(writer.get_extra_info('peername')[0])
        if not any(peer in net for net in networks):
            raise ValueError('Untrusted AudioSocket peer')
        kind, body = await asyncio.wait_for(packet(reader), 5)
        if kind != 1 or len(body) != 16:
            raise ValueError('Expected AudioSocket call UUID')
        call_id = 'ast:'+str(uuid.UUID(bytes=body))
        prepared = await prepare(route, call_id)
        tenant = prepared['tenant']
        conversation = prepared['conversation']
        record_session = prepared['record_session']
        session = prepared['session']
        message_ids = {}
        async def transcript(role, text, item_id):
            key = (role, item_id)
            if item_id and key in message_ids:
                await db.pool().execute('UPDATE messages SET content=$3 WHERE conversation_id=$1 AND id=$2',
                                        conversation, message_ids[key], text)
            else:
                ident = await db.pool().fetchval('INSERT INTO messages(conversation_id,role,content) VALUES($1,$2,$3) RETURNING id',
                                                 conversation, role, text)
                if item_id:
                    message_ids[key] = ident
        async def tool(name, args):
            return await run_phone_tool(tenant, record_session, conversation, call_id, name, args, recording)
        async def monitor():
            while True:
                await asyncio.sleep(5)
                if recording.started is not None and not await channel_authorization.is_authorized(tenant['id'], 'call_recording'):
                    recording.discard()
                    record_session['recording_consent'] = False
                if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
                    raise ValueError('Business telephone authorization revoked')
        settings = get_settings()
        provider = settings.phone_voice_provider
        async with provider_connection(settings, provider) as ws:
            media = asyncio.create_task(MediaBridge(reader, writer, ws, session, transcript, tool, recording,
                                                    provider=provider).run())
            guard = asyncio.create_task(monitor())
            try:
                done, _ = await asyncio.wait((media, guard), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                media.cancel(); guard.cancel()
                await asyncio.gather(media, guard, return_exceptions=True)
        status = 'completed'
    except asyncio.IncompleteReadError:
        status = 'disconnected'
        reason = 'The audio stream closed before the call ended'
    except Exception as error:
        # Keep the message: "RuntimeError" alone cost a whole debugging session
        # after a real call went silent.
        log.warning('Asterisk call ended (%s): %s', type(error).__name__, str(error)[:500])
        reason = f'{type(error).__name__}: {str(error)[:300]}'
    finally:
        if tenant and conversation:
            try:
                body = recording.wav()
                if body and record_session:
                    try:
                        await voice_records.store_audio(record_session, body, 'audio/wav')
                    except Exception:
                        log.exception('Telephone recording could not be saved')
                await finish(tenant, call_id, conversation, status, record_session, reason=reason)
                if record_session:
                    request = await db.pool().fetchval('UPDATE voice_sessions SET finalized_at=now() WHERE id=$1 RETURNING delivery_request', record_session['id'])
                    await voice_records.complete_delivery(record_session, tenant, request, {'ok':True})
            except Exception:
                log.exception('Asterisk call finalization requires reconciliation')
        writer.close()
        await writer.wait_closed()


async def main():
    routes = routes_from_json(os.environ['ASTERISK_ROUTES'])
    host = os.environ.get('ASTERISK_BIND', '127.0.0.1')
    networks = [ipaddress.ip_network(s.strip()) for s in os.environ.get('ASTERISK_PEERS', '127.0.0.1/32,::1/128').split(',')]
    if any(n.prefixlen == 0 for n in networks):
        raise ValueError('An unrestricted AudioSocket peer network is forbidden')
    await db.init()
    servers = []
    try:
        for route in routes:
            server = await asyncio.start_server(lambda r,w,route=route:handle(r,w,route,networks), host, route.port)
            servers.append(server)
            log.info('Business %s private phone listener ready on %s:%s', route.tenant, host, route.port)
        await asyncio.gather(*(s.serve_forever() for s in servers))
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()
        await db.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
