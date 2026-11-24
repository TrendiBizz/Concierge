import asyncio
import base64
import json
import struct
from types import SimpleNamespace

import pytest
from app import asterisk_bridge
from app.asterisk_bridge import (
    MAX_ERRORS,
    MediaBridge,
    Route,
    downsample_24k_to_8k,
    packet,
    routes_from_json,
    strip_additional_properties,
    upsample_8k_to_16k,
)
from app.config import Settings


def test_routes_cannot_share_destination_or_port():
    a = {'tenant': 'alpha', 'number': '+6495550100', 'port': 9101}
    b = {'tenant': 'beta', 'number': '+6495550101', 'port': 9102}
    assert len(routes_from_json(json.dumps([a, b]))) == 2
    for bad in ({**b, 'port': 9101}, {**b, 'number': a['number']}):
        with pytest.raises(ValueError):
            routes_from_json(json.dumps([a, bad]))


def test_gemini_config_defaults_and_ws_url():
    s = Settings(_env_file=None)
    assert s.phone_voice_provider == 'gemini_live'
    assert s.gemini_live_model == 'models/gemini-3.8-live'
    assert s.gemini_live_voice == 'Aoede'
    assert s.gemini_thinking_level == 'low'
    assert 'BidiGenerateContent' in s.gemini_live_ws_url
    assert s.gemini_ws_url == s.gemini_live_ws_url

    with_key = Settings(_env_file=None, gemini_api_key='test-key-123')
    assert with_key.gemini_ws_url == f'{with_key.gemini_live_ws_url}?key=test-key-123'

    with_query = Settings(
        _env_file=None,
        gemini_api_key='test-key-123',
        gemini_live_ws_url='ws://127.0.0.1:9999/live?alt=json',
    )
    assert with_query.gemini_ws_url == 'ws://127.0.0.1:9999/live?alt=json&key=test-key-123'

    assert Settings(_env_file=None, phone_voice_provider='grok').phone_voice_provider == 'grok'
    assert Settings(_env_file=None, phone_voice_provider='legacy_twilio_tts').phone_voice_provider == 'legacy_twilio_tts'


def test_audio_resampling_8k_to_16k_and_24k_to_8k():
    # Silence preserves length ratios (2x up, 3:1 down)
    assert upsample_8k_to_16k(b'\0' * 320) == b'\0' * 640
    assert downsample_24k_to_8k(b'\0' * 960) == b'\0' * 320

    # Linear interpolation on ramp 8k -> 16k
    ramp = struct.pack('<3h', 0, 100, -100)
    up = struct.unpack('<6h', upsample_8k_to_16k(ramp))
    assert up == (0, 50, 100, 0, -100, -100)

    # Boxcar 3:1 average 24k -> 8k (positive and negative values)
    pcm24 = struct.pack('<6h', 300, 600, 900, -300, -600, -900)
    down = struct.unpack('<2h', downsample_24k_to_8k(pcm24))
    assert down == (600, -600)

    # Odd byte length rejected
    with pytest.raises(ValueError):
        upsample_8k_to_16k(b'\x00\x01\x02')
    with pytest.raises(ValueError):
        downsample_24k_to_8k(b'\x00\x01\x02')


def test_strip_additional_properties_recursively():
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'nested': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {'x': {'type': 'string'}},
            },
            'items': [{'type': 'object', 'additionalProperties': False}],
        },
    }
    cleaned = strip_additional_properties(schema)
    assert 'additionalProperties' not in cleaned
    assert 'additionalProperties' not in cleaned['properties']['nested']
    assert 'additionalProperties' not in cleaned['properties']['items'][0]
    assert cleaned['properties']['nested']['properties']['x'] == {'type': 'string'}


def test_register_requires_gemini_live_provider_and_api_key(monkeypatch):
    route = Route('alpha', '+6495550100', 9101)
    for overrides in (
        {'phone_receptionist_enabled': False, 'phone_voice_provider': 'gemini_live', 'gemini_api_key': 'k'},
        {'phone_receptionist_enabled': True, 'phone_voice_provider': 'grok', 'gemini_api_key': 'k'},
        {'phone_receptionist_enabled': True, 'phone_voice_provider': 'gemini_live', 'gemini_api_key': ''},
    ):
        monkeypatch.setattr(asterisk_bridge, 'get_settings', lambda o=overrides: SimpleNamespace(**o))
        with pytest.raises(ValueError, match='Phone receptionist is disabled'):
            asyncio.run(asterisk_bridge.register(route, 'ast:test'))


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


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.005)


@pytest.mark.hangs_on_py312
def test_two_concurrent_businesses_audio_transcript_tools_and_barge_in_are_isolated():
    async def scenario():
        results = {}
        tasks = []
        servers = []
        clients = []
        sample_tools = [
            {
                'type': 'function',
                'name': 'search_knowledge',
                'description': 'Search business facts',
                'parameters': {
                    'type': 'object',
                    'properties': {'query': {'type': 'string'}},
                    'required': ['query'],
                    'additionalProperties': False,
                },
            },
            {
                'type': 'function',
                'name': 'end_call',
                'description': 'End after goodbye',
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
            },
        ]
        try:
            for index, business in enumerate(('alpha', 'beta')):
                ws = Socket()
                turns, tools = [], []

                async def transcript(role, text, item_id, turns=turns):
                    turns.append((role, text, item_id))

                async def tool(name, args, tools=tools, business=business):
                    tools.append((business, name, args))
                    return {'business': business}

                async def connected(reader, writer, ws=ws, business=business, transcript=transcript, tool=tool):
                    session = {'instructions': business, 'tools': sample_tools}
                    task = asyncio.create_task(MediaBridge(reader, writer, ws, session, transcript, tool).run())
                    tasks.append(task)

                server = await asyncio.start_server(connected, '127.0.0.1', 0)
                servers.append(server)
                reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
                clients.append(writer)
                audio8 = bytes([index + 1, 0]) * 160
                audio24 = bytes([index + 1, 0]) * 480
                results[business] = (ws, turns, tools, reader, writer, audio8, audio24)

            for business, (ws, turns, tools, reader, writer, audio8, audio24) in results.items():
                await until(lambda: ws.sent)
                setup = ws.sent[0]['setup']
                assert setup['systemInstruction']['parts'][0]['text'] == business
                assert setup['model'] == 'models/gemini-3.8-live'
                assert setup['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Aoede'
                assert setup['generationConfig']['thinkingConfig']['thinkingLevel'] == 'low'
                assert setup['inputAudioTranscription'] == {}
                assert setup['outputAudioTranscription'] == {}
                assert setup['contextWindowCompression'] == {'slidingWindow': {}}
                decls = {d['name']: d for d in setup['tools'][0]['functionDeclarations']}
                assert 'additionalProperties' not in decls['search_knowledge']['parameters']
                assert 'parameters' not in decls['end_call']

                await ws.inbox.put({'setupComplete': {}})
                await until(lambda: any('clientContent' in e for e in ws.sent))

                writer.write(struct.pack('!BH', 0x10, len(audio8)) + audio8)
                await writer.drain()

                # Send 24kHz Gemini audio -> bridge downsamples to 8kHz AudioSocket
                await ws.inbox.put({
                    'serverContent': {
                        'modelTurn': {
                            'parts': [{
                                'inlineData': {
                                    'mimeType': 'audio/pcm;rate=24000',
                                    'data': base64.b64encode(audio24).decode(),
                                }
                            }]
                        }
                    }
                })
                await ws.inbox.put({'serverContent': {'inputTranscription': {'text': business + ' enquiry'}}})
                await ws.inbox.put({'serverContent': {'inputTranscription': {'text': ' complete'}}})
                await ws.inbox.put({
                    'toolCall': {
                        'functionCalls': [
                            {'id': 'same-tool-id', 'name': 'search_knowledge', 'args': {'query': business}},
                            {'id': 'same-tool-id', 'name': 'search_knowledge', 'args': {'query': 'duplicate'}},
                        ]
                    }
                })
                await ws.inbox.put({'serverContent': {'turnComplete': True}})

            for business, (ws, turns, tools, reader, writer, audio8, audio24) in results.items():
                kind, body = await asyncio.wait_for(packet(reader), 2)
                assert kind == 0x10 and body == audio8
                await until(lambda: len(turns) == 2 and tools and any('realtimeInput' in e for e in ws.sent))
                assert turns == [
                    ('user', business + ' enquiry', 'user-1'),
                    ('user', business + ' enquiry complete', 'user-1'),
                ]
                assert tools == [(business, 'search_knowledge', {'query': business})]
                rt_audio = next(e['realtimeInput']['audio'] for e in ws.sent if 'realtimeInput' in e)
                assert rt_audio['mimeType'] == 'audio/pcm;rate=16000'
                assert base64.b64decode(rt_audio['data']) == upsample_8k_to_16k(audio8)
                tool_resps = [e['toolResponse']['functionResponses'] for e in ws.sent if 'toolResponse' in e]
                assert tool_resps == [[{'id': 'same-tool-id', 'name': 'search_knowledge', 'response': {'business': business}}]]

                # Barge-in (serverContent.interrupted) flushes buffered playback
                await ws.inbox.put({
                    'serverContent': {
                        'modelTurn': {
                            'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000',
                                                      'data': base64.b64encode(audio24 * 10).decode()}}]
                        }
                    }
                })
                await ws.inbox.put({'serverContent': {'interrupted': True}})
                await asyncio.sleep(.05)
                writer.write(b'\x00\x00\x00')
                await writer.drain()
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for writer in clients:
                writer.close()
                await writer.wait_closed()
            for server in servers:
                server.close()
                await server.wait_closed()
    asyncio.run(scenario())


def test_shared_sip_provider_has_exact_destination_mapping_and_unknown_rejection():
    import runpy
    from pathlib import Path
    renderer = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/asterisk/render_routes.py'))['render']
    rows = [{'tenant': 'alpha', 'number': '+6495550100', 'port': 9101, 'source_cidr': '192.0.2.10/32'},
            {'tenant': 'beta', 'number': '+6495550101', 'port': 9102, 'source_cidr': '192.0.2.10/32'}]
    extensions, pjsip = renderer(rows, 'bridge')
    assert 'exten => +6495550100,1,Goto(business-alpha,s,1)' in extensions
    assert 'exten => +6495550101,1,Goto(business-beta,s,1)' in extensions
    assert 'exten => _.,1,Hangup(21)' in extensions
    assert 'bridge:9101' in extensions and 'bridge:9102' in extensions
    assert pjsip.count('type=endpoint') == 1
    with pytest.raises(ValueError):
        renderer([rows[0], {**rows[1], 'number': rows[0]['number']}], 'bridge')
    with pytest.raises(ValueError):
        renderer([{**rows[0], 'source_cidr': '0.0.0.0/0'}], 'bridge')


def test_oversized_or_truncated_audio_socket_packets_are_rejected():
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack('!BH', 0x10, 9000))
        with pytest.raises(ValueError):
            await packet(reader)
        reader = asyncio.StreamReader()
        reader.feed_data(struct.pack('!BH', 0x10, 320) + b'\0' * 10)
        reader.feed_eof()
        with pytest.raises(asyncio.IncompleteReadError):
            await packet(reader)
    asyncio.run(scenario())


def test_silent_asterisk_endpoint_supplies_vad_silence_without_cancelling_partial_packet():
    async def scenario():
        reader = asyncio.StreamReader()
        ws = Socket()
        bridge = MediaBridge(reader, None, ws, {}, None, None)
        bridge.ready.set()
        task = asyncio.create_task(bridge.input())
        try:
            audio = b'\x01\x00' * 160
            expected_up = upsample_8k_to_16k(audio)
            frame = struct.pack('!BH', 0x10, len(audio)) + audio
            reader.feed_data(frame[:4])
            await asyncio.sleep(.06)
            assert ws.sent and all(
                e['realtimeInput']['audio']['mimeType'] == 'audio/pcm;rate=16000'
                and base64.b64decode(e['realtimeInput']['audio']['data']) == b'\0' * 640
                for e in ws.sent
            )
            reader.feed_data(frame[4:])
            await until(lambda: any(
                base64.b64decode(e['realtimeInput']['audio']['data']) == expected_up
                for e in ws.sent
            ))
            reader.feed_data(b'\0\0\0')
            await asyncio.wait_for(task, 1)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


class Writer:
    """Captures the AudioSocket packets the bridge would send to the caller."""
    def __init__(self):
        self.sent = bytearray()

    def write(self, data):
        self.sent.extend(data)

    async def drain(self):
        pass


def test_gemini_session_errors_tolerate_transient_faults_and_fail_at_max_errors():
    async def scenario():
        ws = Socket()
        writer = Writer()
        bridge = MediaBridge(None, writer, ws, {}, None, None)
        tasks = [asyncio.create_task(bridge.gemini()), asyncio.create_task(bridge.output())]
        try:
            await ws.inbox.put({'setupComplete': {}})
            await until(lambda: any('clientContent' in e for e in ws.sent))
            for _ in range(MAX_ERRORS - 1):
                await ws.inbox.put({'error': {'code': 500, 'message': 'transient'}})
                await asyncio.sleep(.01)
            assert not tasks[0].done(), 'transient errors below MAX_ERRORS must not end the call'
            await ws.inbox.put({'error': {'code': 500, 'message': 'boom'}})
            with pytest.raises(RuntimeError):
                await asyncio.wait_for(tasks[0], 2)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.run(scenario())


def test_interrupted_server_content_flushes_playback_and_unaligned_24k_chunks_carry_over():
    async def scenario():
        ws = Socket()
        writer = Writer()
        bridge = MediaBridge(None, writer, ws, {}, None, None)
        task = asyncio.create_task(bridge.gemini())
        try:
            await ws.inbox.put({'setupComplete': {}})
            await until(lambda: any('clientContent' in e for e in ws.sent))
            # Split 6 samples (12 bytes) across 4 bytes + 8 bytes (unaligned to 6-byte triplets)
            pcm24 = struct.pack('<6h', 300, 300, 300, 600, 600, 600)
            await ws.inbox.put({
                'serverContent': {
                    'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000',
                                                            'data': base64.b64encode(pcm24[:4]).decode()}}]}
                }
            })
            await ws.inbox.put({
                'serverContent': {
                    'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000',
                                                            'data': base64.b64encode(pcm24[4:]).decode()}}]}
                }
            })
            await until(lambda: len(bridge.playback) == 4)
            assert struct.unpack('<2h', bytes(bridge.playback)) == (300, 600)

            bridge.ending = True
            await ws.inbox.put({'serverContent': {'interrupted': True}})
            await until(lambda: not bridge.playback and not bridge.ending)
            assert bridge.speaking is False
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_an_unanswered_caller_turn_is_prompted_once_instead_of_going_silent():
    async def scenario():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None, reply_nudge=.2)
        bridge.reply_pending = True
        bridge.reply_since = asyncio.get_running_loop().time()
        task = asyncio.create_task(bridge.watchdog())
        try:
            await until(lambda: any('clientContent' in e for e in ws.sent))
            assert sum('clientContent' in e for e in ws.sent) == 1
            await asyncio.sleep(.4)
            assert sum('clientContent' in e for e in ws.sent) == 1, 'one nudge per turn'
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
