"""OpenAI Realtime provider for the Asterisk bridge, offline against a scripted fake socket."""
import asyncio
import base64
import json
import math
import struct

import pytest

from app import voice_openai
from app.asterisk_bridge import MAX_ERRORS, MediaBridge, packet
from app.config import Settings


class Socket:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.sent = []

    async def send(self, value):
        self.sent.append(json.loads(value))

    def __aiter__(self):
        return self

    async def __anext__(self):
        return json.dumps(await self.inbox.get())

    def types(self):
        return [e.get('type') for e in self.sent]


class Writer:
    def __init__(self):
        self.sent = bytearray()

    def write(self, data):
        self.sent.extend(data)

    async def drain(self):
        pass


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.005)


def ulaw_b64(n_samples, level=3000):
    pcm = struct.pack(f'<{n_samples}h', *([level] * n_samples))
    return base64.b64encode(voice_openai.pcm16_to_ulaw(pcm)).decode()


def run_bridge(scenario, **kw):
    async def main():
        ws = Socket()
        bridge = MediaBridge(kw.pop('reader', None), kw.pop('writer', None), ws, kw.pop('session', {}),
                             kw.pop('on_transcript', None), kw.pop('on_tool', None),
                             provider='openai_realtime', **kw)
        task = asyncio.create_task(bridge.openai())
        try:
            await scenario(ws, bridge)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(main())


# --- config and pure protocol pieces -------------------------------------------------------------

def test_settings_defaults_and_phone_voice_ready_per_provider():
    s = Settings(_env_file=None)
    assert s.phone_voice_provider == 'gemini_live'
    assert s.openai_realtime_model == 'gpt-realtime'
    assert s.openai_turn_detection == 'semantic_vad'
    on = dict(_env_file=None, phone_receptionist_enabled=True)
    assert not Settings(**on).phone_voice_ready
    assert Settings(**on, gemini_api_key='g').phone_voice_ready
    # an OpenAI key alone must not switch a Gemini line on, and a Gemini key must not satisfy OpenAI
    assert not Settings(**on, openai_api_key='o').phone_voice_ready
    assert Settings(**on, phone_voice_provider='openai_realtime', openai_api_key='o').phone_voice_ready
    assert not Settings(**on, phone_voice_provider='openai_realtime', gemini_api_key='g').phone_voice_ready
    assert not Settings(_env_file=None, phone_voice_provider='openai_realtime', openai_api_key='o').phone_voice_ready
    assert not Settings(**on, phone_voice_provider='openai_realtime', openai_api_key='   ').phone_voice_ready


def test_ulaw_known_values_and_round_trip_error_is_small():
    assert voice_openai.pcm16_to_ulaw(struct.pack('<h', 0)) == b'\xff'
    assert struct.unpack('<h', voice_openai.ulaw_to_pcm16(b'\xff'))[0] == 0
    samples = [int(12000 * math.sin(i / 7)) for i in range(800)] + [-32768, 32767, -1, 1, 0]
    pcm = struct.pack(f'<{len(samples)}h', *samples)
    back = struct.unpack(f'<{len(samples)}h', voice_openai.ulaw_to_pcm16(voice_openai.pcm16_to_ulaw(pcm)))
    for original, decoded in zip(samples, back):
        # mu-law keeps ~13 bits of dynamic range: error stays under ~3.5% of the sample (+ clip floor)
        assert abs(original - decoded) <= max(40, abs(original) * 0.04) + (1200 if abs(original) > 32000 else 0)
    with pytest.raises(ValueError):
        voice_openai.pcm16_to_ulaw(b'\x01')


def test_session_update_is_pcmu_with_tools_and_safe_voice_fallback():
    tools = [{'name': 'capture_lead', 'description': 'd', 'parameters': {'type': 'object', 'properties': {'a': {}}}},
             {'name': 'end_call'}, {'description': 'nameless'}, 'junk']
    event = voice_openai.session_update(model='gpt-realtime', voice='not-a-voice', instructions='be brief',
                                        tools=tools, transcribe_model='gpt-4o-mini-transcribe', turn='semantic_vad')
    sess = event['session']
    assert event['type'] == 'session.update' and sess['instructions'] == 'be brief'
    assert sess['audio']['input']['format'] == {'type': 'audio/pcmu'}
    assert sess['audio']['output']['format'] == {'type': 'audio/pcmu'}
    assert sess['audio']['output']['voice'] == 'marin'
    assert [t['name'] for t in sess['tools']] == ['capture_lead', 'end_call']
    assert all(t['type'] == 'function' for t in sess['tools'])
    td = sess['audio']['input']['turn_detection']
    assert td['type'] == 'semantic_vad' and td['interrupt_response'] is True
    server = voice_openai.turn_detection('server_vad')
    assert server['silence_duration_ms'] == 700 and server['interrupt_response'] is True


def test_websocket_key_goes_in_a_header_never_the_url():
    s = Settings(_env_file=None, openai_api_key='sk-secret')
    url, headers = voice_openai.ws_request(s)
    assert 'sk-secret' not in url and url.endswith('?model=gpt-realtime')
    assert headers == {'Authorization': 'Bearer sk-secret'}


# --- bridge behaviour ---------------------------------------------------------------------------

def test_session_updated_sends_setup_then_one_greeting():
    async def scenario(ws, bridge):
        await until(lambda: ws.types() == ['session.update'])
        await ws.inbox.put({'type': 'session.created'})
        await ws.inbox.put({'type': 'session.updated'})
        await ws.inbox.put({'type': 'session.updated'})
        await until(lambda: 'response.create' in ws.types())
        await asyncio.sleep(.05)
        assert ws.types() == ['session.update', 'conversation.item.create', 'response.create']
        assert bridge.ready.is_set()
    run_bridge(scenario, session={'instructions': 'hi'})


def test_audio_delta_is_decoded_to_8k_pcm_and_queued():
    async def scenario(ws, bridge):
        await ws.inbox.put({'type': 'response.output_audio.delta', 'item_id': 'i1', 'delta': ulaw_b64(160)})
        await until(lambda: len(bridge.playback) == 320)
        assert bridge.speaking is True
        value = struct.unpack('<h', bytes(bridge.playback[:2]))[0]
        assert abs(value - 3000) < 150
        # the beta event name is accepted too
        await ws.inbox.put({'type': 'response.audio.delta', 'item_id': 'i1', 'delta': ulaw_b64(160)})
        await until(lambda: len(bridge.playback) == 640)
    run_bridge(scenario)


def test_caller_interruption_clears_playback_and_truncates_at_what_was_heard():
    async def scenario(ws, bridge):
        # 400 ms of speech queued (6400 bytes); 100 ms (1600 bytes) already sent to the caller
        await ws.inbox.put({'type': 'response.output_audio.delta', 'item_id': 'item_9', 'delta': ulaw_b64(3200)})
        await until(lambda: len(bridge.playback) == 6400)
        del bridge.playback[:1600]
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await until(lambda: 'conversation.item.truncate' in ws.types())
        truncate = next(e for e in ws.sent if e['type'] == 'conversation.item.truncate')
        assert truncate == {'type': 'conversation.item.truncate', 'item_id': 'item_9',
                            'content_index': 0, 'audio_end_ms': 100}
        assert not bridge.playback and bridge.speaking is False and bridge.caller_speaking is True
        # a second speech_started with nothing playing must not send another truncate
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await asyncio.sleep(.05)
        assert ws.types().count('conversation.item.truncate') == 1
    run_bridge(scenario)


def test_interruption_with_nothing_playing_keeps_a_pending_hangup():
    async def scenario(ws, bridge):
        bridge.ending = True
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await until(lambda: bridge.caller_speaking)
        await asyncio.sleep(.02)
        assert bridge.ending is True, 'a cough after the goodbye must not cancel the hang-up'
    run_bridge(scenario)


def test_tool_call_runs_once_replies_with_output_then_asks_for_the_next_response():
    calls = []

    async def on_tool(name, args):
        calls.append((name, args))
        return {'ok': True, 'saved': args.get('name')}

    async def scenario(ws, bridge):
        event = {'type': 'response.function_call_arguments.done', 'call_id': 'c1',
                 'name': 'capture_lead', 'arguments': json.dumps({'name': 'Sam'})}
        await ws.inbox.put(event)
        await ws.inbox.put(event)  # replayed id must be ignored
        await until(lambda: 'conversation.item.create' in ws.types())
        await asyncio.sleep(.05)
        assert calls == [('capture_lead', {'name': 'Sam'})]
        out = next(e for e in ws.sent if e['type'] == 'conversation.item.create')['item']
        assert out['type'] == 'function_call_output' and out['call_id'] == 'c1'
        assert json.loads(out['output']) == {'ok': True, 'saved': 'Sam'}
        assert 'response.create' not in ws.types(), 'the model must finish its turn before we continue it'
        await ws.inbox.put({'type': 'response.done'})
        await until(lambda: 'response.create' in ws.types())
    run_bridge(scenario, on_tool=on_tool)


def test_end_call_marks_ending_without_a_tool_run_or_a_follow_up_response():
    async def on_tool(name, args):  # pragma: no cover - must not run
        raise AssertionError('end_call is handled by the bridge')

    async def scenario(ws, bridge):
        await ws.inbox.put({'type': 'response.function_call_arguments.done', 'call_id': 'e1',
                            'name': 'end_call', 'arguments': '{}'})
        await until(lambda: bridge.ending)
        await ws.inbox.put({'type': 'response.done'})
        await asyncio.sleep(.05)
        assert 'response.create' not in ws.types() and 'conversation.item.create' not in ws.types()
    run_bridge(scenario, on_tool=on_tool)


def test_bad_tool_arguments_and_tool_flood_are_rejected():
    async def on_tool(name, args):
        return {}

    async def main():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, on_tool, provider='openai_realtime')
        task = asyncio.create_task(bridge.openai())
        await ws.inbox.put({'type': 'response.function_call_arguments.done', 'call_id': 'x',
                            'name': 't', 'arguments': '[1]'})
        with pytest.raises(ValueError):
            await asyncio.wait_for(task, 2)
        bridge = MediaBridge(None, None, ws, {}, None, on_tool, provider='openai_realtime')
        bridge.seen_tools = {f'id{i}' for i in range(40)}
        task = asyncio.create_task(bridge.openai())
        await ws.inbox.put({'type': 'response.function_call_arguments.done', 'call_id': 'new',
                            'name': 't', 'arguments': '{}'})
        with pytest.raises(ValueError, match='Tool limit'):
            await asyncio.wait_for(task, 2)
    asyncio.run(main())


def test_housekeeping_errors_are_ignored_but_real_errors_end_the_call_at_the_limit():
    async def main():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None, provider='openai_realtime')
        task = asyncio.create_task(bridge.openai())
        for _ in range(MAX_ERRORS + 2):
            await ws.inbox.put({'type': 'error', 'error': {'code': 'x', 'message': 'Cannot truncate: item already finished'}})
            await ws.inbox.put({'type': 'error', 'error': {'code': 'response_cancel_not_active', 'message': 'nothing to cancel'}})
        await asyncio.sleep(.05)
        assert bridge.errors == 0 and not task.done()
        for _ in range(MAX_ERRORS - 1):
            await ws.inbox.put({'type': 'error', 'error': {'code': 'server_error', 'message': 'blip'}})
        await asyncio.sleep(.05)
        assert not task.done()
        await ws.inbox.put({'type': 'error', 'error': {'code': 'server_error', 'message': 'boom'}})
        with pytest.raises(RuntimeError, match='OpenAI Realtime'):
            await asyncio.wait_for(task, 2)
    asyncio.run(main())


def test_transcripts_are_stored_caller_first_even_when_transcription_is_late():
    saved = []

    async def on_transcript(role, text, item_id):
        saved.append((role, text))

    async def scenario(ws, bridge):
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await ws.inbox.put({'type': 'input_audio_buffer.speech_stopped'})
        # the assistant finishes speaking before the caller's words are transcribed
        await ws.inbox.put({'type': 'response.output_audio_transcript.delta', 'item_id': 'a1', 'delta': 'Sure, '})
        await ws.inbox.put({'type': 'response.output_audio_transcript.done', 'item_id': 'a1', 'transcript': 'Sure, what is your name?'})
        await asyncio.sleep(.05)
        assert saved == [], 'assistant line must wait for the caller line it answers'
        await ws.inbox.put({'type': 'conversation.item.input_audio_transcription.completed',
                            'item_id': 'u1', 'transcript': 'Hi there'})
        await until(lambda: len(saved) == 2)
        assert saved == [('user', 'Hi there'), ('assistant', 'Sure, what is your name?')]
    run_bridge(scenario, on_transcript=on_transcript)


def test_untranscribed_noise_does_not_swallow_the_assistant_reply():
    saved = []

    async def on_transcript(role, text, item_id):
        saved.append((role, text))

    async def scenario(ws, bridge):
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await ws.inbox.put({'type': 'response.output_audio_transcript.done', 'item_id': 'a1', 'transcript': 'Hello?'})
        await ws.inbox.put({'type': 'response.done'})
        await until(lambda: saved == [('assistant', 'Hello?')])
    run_bridge(scenario, on_transcript=on_transcript)


def test_interrupted_reply_is_still_saved_with_the_words_spoken_so_far():
    saved = []

    async def on_transcript(role, text, item_id):
        saved.append((role, text))

    async def scenario(ws, bridge):
        await ws.inbox.put({'type': 'response.output_audio.delta', 'item_id': 'a1', 'delta': ulaw_b64(160)})
        await ws.inbox.put({'type': 'response.output_audio_transcript.delta', 'item_id': 'a1', 'delta': 'Our hours are'})
        await until(lambda: bridge.speaking and bridge._oa_text.get('a1'))
        await ws.inbox.put({'type': 'input_audio_buffer.speech_started'})
        await ws.inbox.put({'type': 'conversation.item.input_audio_transcription.completed',
                            'item_id': 'u1', 'transcript': 'stop'})
        await until(lambda: len(saved) == 2)
        assert saved == [('user', 'stop'), ('assistant', 'Our hours are')]
    run_bridge(scenario, on_transcript=on_transcript)


def test_unanswered_turn_is_nudged_once_with_openai_events():
    async def main():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None, reply_nudge=.2, provider='openai_realtime')
        bridge.reply_pending = True
        bridge.reply_since = asyncio.get_running_loop().time()
        task = asyncio.create_task(bridge.watchdog())
        try:
            await until(lambda: 'response.create' in ws.types())
            await asyncio.sleep(.4)
            assert ws.types() == ['conversation.item.create', 'response.create']
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(main())


def test_caller_audio_is_sent_as_mu_law_without_resampling():
    async def main():
        frame = struct.pack('<160h', *([1000] * 160))
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack('!BH', 0x10, len(frame)) + frame)
        ws = Socket()
        bridge = MediaBridge(reader, None, ws, {}, None, None, provider='openai_realtime')
        bridge.ready.set()
        task = asyncio.create_task(bridge.input())
        try:
            await until(lambda: any(e.get('type') == 'input_audio_buffer.append' for e in ws.sent))
            sent = next(e for e in ws.sent if e.get('type') == 'input_audio_buffer.append')
            audio = base64.b64decode(sent['audio'])
            assert len(audio) == 160, '20 ms at 8 kHz is 160 mu-law bytes'
            assert abs(struct.unpack('<h', voice_openai.ulaw_to_pcm16(audio[:1]))[0] - 1000) < 60
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(main())


def test_gemini_path_is_unchanged_by_the_provider_switch():
    bridge = MediaBridge(None, None, None, {'instructions': 'hi'}, None, None)
    assert bridge.provider == 'gemini_live'
    assert 'setup' in bridge._setup_payload()
