"""OpenAI Realtime protocol pieces for the Asterisk telephone bridge.

Pure functions only (no sockets), so they are unit-testable offline. The bridge in
`asterisk_bridge.MediaBridge` owns the sockets and the call state.

Audio: the bridge asks OpenAI for 8 kHz G.711 mu-law (`audio/pcmu`) in both directions, which is
exactly what a carrier trunk carries, so there is no resampling for this provider. Mu-law is
decoded to the PCM16 8 kHz the AudioSocket writer already expects.

UNVERIFIED against the live service until a key is added and `QA/verification/voice_ab_harness.py
--live` has been run: event names follow OpenAI's published GA Realtime API (`gpt-realtime`).
"""
from __future__ import annotations

from array import array
import sys

OPENAI_VOICES = frozenset({
    'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse', 'marin', 'cedar',
})

# 16-bit mono at 8 kHz = 16 bytes per millisecond. Used to turn queued bytes into milliseconds.
PCM16_8K_BYTES_PER_MS = 16

# Server errors that follow our own interruption housekeeping (truncating an item that has already
# finished, cancelling a response that is not running). They are expected and must not count
# toward the session's error limit.
BENIGN_ERROR_MARKERS = ('truncat', 'cancel')

_BIAS = 0x84
_CLIP = 32635


def _encode_sample(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0
    if sample < 0:
        sample = -sample
    sample = min(sample, _CLIP) + _BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not sample & mask:
        exponent -= 1
        mask >>= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def _decode_byte(byte: int) -> int:
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return -sample if sign else sample


_DECODE = array('h', (_decode_byte(b) for b in range(256)))
_ENCODE: bytes | None = None


def _encode_table() -> bytes:
    global _ENCODE
    if _ENCODE is None:
        _ENCODE = bytes(_encode_sample(s) for s in range(-32768, 32768))
    return _ENCODE


def ulaw_to_pcm16(data: bytes) -> bytes:
    """G.711 mu-law bytes to PCM16 little-endian."""
    out = array('h', (_DECODE[b] for b in data))
    if sys.byteorder != 'little':
        out.byteswap()
    return out.tobytes()


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """PCM16 little-endian to G.711 mu-law bytes."""
    if len(pcm) % 2:
        raise ValueError('Invalid PCM16 frame')
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    table = _encode_table()
    return bytes(table[s + 32768] for s in samples)


def function_tools(tools) -> list[dict]:
    """Flat tool specs to Realtime function tools."""
    out = []
    for tool in tools or ():
        if not isinstance(tool, dict) or not tool.get('name'):
            continue
        out.append({
            'type': 'function',
            'name': tool['name'],
            'description': tool.get('description', ''),
            'parameters': tool.get('parameters') or {'type': 'object', 'properties': {}},
        })
    return out


def turn_detection(kind: str) -> dict:
    """Telephone turn taking. 700 ms of silence matches the Gemini path: callers pause mid-number."""
    if kind == 'server_vad':
        return {'type': 'server_vad', 'threshold': 0.5, 'prefix_padding_ms': 300,
                'silence_duration_ms': 700, 'create_response': True, 'interrupt_response': True}
    return {'type': 'semantic_vad', 'eagerness': 'medium',
            'create_response': True, 'interrupt_response': True}


PCMU = {'type': 'audio/pcmu'}
PCM24 = {'type': 'audio/pcm', 'rate': 24000}


def session_update(*, model: str, voice: str, instructions: str, tools, transcribe_model: str,
                   turn: str, audio_format: dict | None = None) -> dict:
    fmt = dict(audio_format or PCMU)
    session = {
        'type': 'realtime',
        'model': model,
        'output_modalities': ['audio'],
        'instructions': instructions or '',
        'audio': {
            'input': {
                'format': dict(fmt),
                'transcription': {'model': transcribe_model},
                'turn_detection': turn_detection(turn),
            },
            'output': {
                'format': dict(fmt),
                'voice': voice if voice in OPENAI_VOICES else 'marin',
            },
        },
        'tool_choice': 'auto',
    }
    declared = function_tools(tools)
    if declared:
        session['tools'] = declared
    return {'type': 'session.update', 'session': session}


def web_client_secret_body(session: dict, *, ttl_seconds: int, transcribe_model: str, turn: str) -> dict:
    """Body for POST /v1/realtime/client_secrets: the website session locked server-side.

    Same instructions and tools as Gemini web voice (`voice.build_session`), 24 kHz PCM16 audio, which is
    what the widget already captures and plays, so the browser does no extra resampling.
    """
    update = session_update(model=session['model'], voice=session.get('voice') or 'marin',
                            instructions=session.get('instructions') or '', tools=session.get('tools'),
                            transcribe_model=transcribe_model, turn=turn, audio_format=PCM24)
    return {'expires_after': {'anchor': 'created_at', 'seconds': max(10, min(int(ttl_seconds), 7200))},
            'session': update['session']}


def user_text_items(text: str) -> list[dict]:
    """A synthetic user line followed by a response request (greeting and unanswered-turn nudge)."""
    return [
        {'type': 'conversation.item.create',
         'item': {'type': 'message', 'role': 'user',
                  'content': [{'type': 'input_text', 'text': text}]}},
        {'type': 'response.create'},
    ]


def is_benign_error(event: dict) -> bool:
    error = event.get('error') if isinstance(event.get('error'), dict) else {}
    text = f"{error.get('code', '')} {error.get('message', '')}".lower()
    return any(marker in text for marker in BENIGN_ERROR_MARKERS)


def ws_request(settings) -> tuple[str, dict]:
    """URL and extra headers for the Realtime WebSocket. The key goes in a header, never the URL."""
    sep = '&' if '?' in settings.openai_realtime_ws_url else '?'
    url = f'{settings.openai_realtime_ws_url}{sep}model={settings.openai_realtime_model}'
    return url, {'Authorization': f'Bearer {settings.openai_api_key}'}
