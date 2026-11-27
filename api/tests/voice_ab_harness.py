"""A/B harness for the telephone realtime providers (Gemini Live vs OpenAI Realtime).

It drives the REAL `MediaBridge` with a scripted caller over an in-process AudioSocket, so what it
measures is what a caller on the phone would experience, minus the carrier. No database, no
Asterisk, no tenant data, no SMS, no real calls. Tools are stubs.

Scenarios (per provider):
  greeting   time from connect to the first audio the caller hears
  answer     time from the caller finishing a question to the first reply audio
  barge_in   caller talks over a long answer: how long the old answer keeps playing (cutoff),
             how long until the reply to the interruption starts, and what the model heard
  tool       caller gives name and number: does the model call capture_lead, how fast, what args

Modes
  python tests/voice_ab_harness.py --selftest
      against built-in fake providers. Free. Proves the harness measures what it claims.
  python tests/voice_ab_harness.py --live openai_realtime gemini_live --yes-spend
      against the real services. COSTS MONEY (a few minutes of audio per provider). Needs
      OPENAI_API_KEY / GEMINI_API_KEY in the environment, and macOS `say` + `afconvert` to make
      the caller's voice. Never run against a customer's number; there is none involved.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import asterisk_bridge  # noqa: E402
from app.asterisk_bridge import FRAME_BYTES, MediaBridge  # noqa: E402

INSTRUCTIONS = (
    "You are the phone receptionist for Test Plumbing, a made-up business. Hours: 9 to 5, Monday to "
    "Friday. The call-out fee is 120 dollars. Greet the caller in one short sentence and ask how you "
    "can help. Keep answers to one or two short sentences, EXCEPT when the caller asks you to explain "
    "in detail: then speak at length, several sentences. When you have the caller's name and phone "
    "number, call capture_lead, then say goodbye briefly and call end_call.")
TOOLS = [
    {'name': 'capture_lead', 'description': "Save the caller's name and phone number.",
     'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'phone': {'type': 'string'}},
                    'required': ['name', 'phone']}},
    {'name': 'end_call', 'description': 'End after saying goodbye.',
     'parameters': {'type': 'object', 'properties': {}}},
]
PHRASES = {
    'question': 'Hello, what are your opening hours?',
    'long_request': 'Please explain in detail everything about how your call-out service works, '
                    'step by step, including what happens when the plumber arrives.',
    'interrupt': 'Sorry to stop you, just tell me the call-out price.',
    'lead': 'Sure. My name is Sam Taylor and my number is oh two one, five five five, oh one double oh.',
}
# Selftest caller lengths. The fake picks its script from these, so they are not arbitrary.
SELFTEST_SECONDS = {'question': 1.1, 'long_request': 2.2, 'interrupt': 1.0, 'lead': 3.3}
CUTOFF_GAP = 0.15  # seconds of quiet that count as "the old answer stopped"


# --- caller audio ---------------------------------------------------------------------------------

def tone(seconds: float, level: int = 6000) -> bytes:
    """Selftest stand-in for speech: a loud tone. Real runs use `say`."""
    n = int(8000 * seconds)
    return struct.pack(f'<{n}h', *(int(level * math.sin(i * 0.35)) for i in range(n)))


def spoken(text: str, cache: Path) -> bytes:
    """The text as 8 kHz mono PCM16, via macOS `say` + `afconvert`."""
    key = cache / (str(abs(hash(text))) + '.wav')
    if not key.exists():
        aiff = cache / (key.stem + '.aiff')
        subprocess.run(['say', '-o', str(aiff), text], check=True)
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@8000', '-c', '1', str(aiff), str(key)], check=True)
    with wave.open(str(key), 'rb') as w:
        assert w.getframerate() == 8000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


# --- fake AudioSocket ------------------------------------------------------------------------------

class Line:
    """The Asterisk side of one call: feeds caller frames in real time, logs what the caller hears."""

    def __init__(self):
        self.reader = asyncio.StreamReader()
        self.heard: list[float] = []  # monotonic time of every non-silent frame sent to the caller
        self.t0 = time.monotonic()

    def write(self, data: bytes) -> None:
        if data[:1] == b'\x10' and any(data[3:]):
            self.heard.append(time.monotonic())

    async def drain(self) -> None:
        pass

    async def say(self, pcm: bytes) -> float:
        """Speak `pcm` into the call at real-time pace. Returns the time the speech ended."""
        start = time.monotonic()
        frames = [pcm[i:i + FRAME_BYTES].ljust(FRAME_BYTES, b'\0') for i in range(0, len(pcm), FRAME_BYTES)]
        for i, frame in enumerate(frames):
            self.reader.feed_data(struct.pack('!BH', 0x10, FRAME_BYTES) + frame)
            await asyncio.sleep(max(0, start + (i + 1) * 0.02 - time.monotonic()))
        return time.monotonic()

    def audio_after(self, t: float) -> list[float]:
        return [x for x in self.heard if x >= t]

    async def first_audio_after(self, t: float, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            later = self.audio_after(t)
            if later:
                return later[0]
            await asyncio.sleep(0.01)
        return None

    async def audio_seconds(self, seconds: float, timeout: float, since: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            later = self.audio_after(since)
            if len(later) >= seconds * 50:
                return True
            await asyncio.sleep(0.02)
        return False

    async def quiet_for(self, seconds: float, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.heard or time.monotonic() - self.heard[-1] >= seconds:
                return True
            await asyncio.sleep(0.02)
        return False


class Call:
    def __init__(self, provider: str, connect):
        self.provider, self.connect = provider, connect
        self.line = Line()
        self.transcript: list[tuple[str, str]] = []
        self.tool_calls: list[tuple[float, str, dict]] = []
        self.task = None
        self.t_connect = 0.0

    async def start(self) -> None:
        self.t_connect = time.monotonic()
        self.task = asyncio.create_task(self._run())
        await asyncio.sleep(0)

    async def _run(self) -> None:
        async def on_transcript(role, text, item_id):
            self.transcript.append((role, text))

        async def on_tool(name, args):
            self.tool_calls.append((time.monotonic(), name, args))
            return {'ok': True}

        session = {'instructions': INSTRUCTIONS, 'tools': TOOLS}
        async with self.connect(self.provider) as ws:
            bridge = MediaBridge(self.line.reader, self.line, ws, session, on_transcript, on_tool,
                                 provider=self.provider)
            await bridge.run()

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.line.reader.feed_eof()


# --- scenarios -------------------------------------------------------------------------------------

def _gap_cutoff(heard: list[float], t_start: float):
    """Seconds after `t_start` until the first quiet gap in the audio the caller hears."""
    later = [x for x in heard if x >= t_start]
    if not later:
        return 0.0, None
    last = later[0]
    for x in later[1:]:
        if x - last >= CUTOFF_GAP:
            return last - t_start, x
        last = x
    return last - t_start, None


async def scenario_greeting(call: Call, voice) -> dict:
    t = await call.line.first_audio_after(call.t_connect, 15)
    return {'first_audio_s': None if t is None else round(t - call.t_connect, 3)}


async def scenario_answer(call: Call, voice) -> dict:
    await call.line.quiet_for(1.0, 30)
    end = await call.line.say(voice('question'))
    first = await call.line.first_audio_after(end, 15)
    await call.line.quiet_for(1.0, 30)
    return {'reply_latency_s': None if first is None else round(first - end, 3)}


async def scenario_barge_in(call: Call, voice) -> dict:
    await call.line.quiet_for(1.0, 30)
    asked = await call.line.say(voice('long_request'))
    flowing = await call.line.audio_seconds(1.0, 25, asked)
    if not flowing:
        return {'error': 'the model never started a long answer, nothing to interrupt'}
    t_int = time.monotonic()
    seen_before = len(call.transcript)
    end = await call.line.say(voice('interrupt'))
    await asyncio.sleep(0.5)
    cutoff, resumed = _gap_cutoff(call.line.heard, t_int)
    reply = None
    if resumed is not None:
        reply = resumed - end
    else:
        later = await call.line.first_audio_after(end + 0.05, 12)
        reply = None if later is None else later - end
    await call.line.quiet_for(1.0, 30)
    return {'cutoff_after_interrupt_s': round(cutoff, 3),
            'reply_to_interrupt_s': None if reply is None else round(reply, 3),
            'heard_after_interrupt': [t for r, t in call.transcript[seen_before:] if r == 'user'][:2]}


async def scenario_tool(call: Call, voice) -> dict:
    await call.line.quiet_for(1.0, 30)
    end = await call.line.say(voice('lead'))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not any(n == 'capture_lead' for _, n, _ in call.tool_calls):
        await asyncio.sleep(0.05)
    hit = next(((t, a) for t, n, a in call.tool_calls if n == 'capture_lead'), None)
    if hit is None:
        return {'tool_called': False}
    args = hit[1]
    digits = ''.join(ch for ch in str(args.get('phone', '')) if ch.isdigit())
    return {'tool_called': True, 'latency_s': round(hit[0] - end, 3), 'args': args,
            'name_ok': 'sam' in str(args.get('name', '')).lower() and 'taylor' in str(args.get('name', '')).lower(),
            'phone_digits': digits, 'phone_ok': digits.endswith('215550100') or digits == '0215550100'}


SCENARIOS = (('greeting', scenario_greeting), ('answer', scenario_answer),
             ('barge_in', scenario_barge_in), ('tool', scenario_tool))


async def run_provider(provider: str, connect, voice, names=None) -> dict:
    """One fresh call per scenario, so one failure cannot poison the next."""
    results = {}
    for name, fn in SCENARIOS:
        if names and name not in names:
            continue
        call = Call(provider, connect)
        await call.start()
        try:
            results[name] = await asyncio.wait_for(fn(call, voice), 120)
            results[name]['transcript'] = call.transcript[-6:]
        except Exception as error:  # noqa: BLE001 - a failed scenario is a result, not a crash
            results[name] = {'error': f'{type(error).__name__}: {error}'}
        finally:
            await call.stop()
    return results


def table(all_results: dict) -> str:
    rows = [('metric', *all_results)]
    def get(provider, scenario, key):
        value = all_results[provider].get(scenario, {}).get(key)
        return 'n/a' if value is None else str(value)
    for scenario, key, label in (
            ('greeting', 'first_audio_s', 'greeting first audio (s)'),
            ('answer', 'reply_latency_s', 'reply latency after caller stops (s)'),
            ('barge_in', 'cutoff_after_interrupt_s', 'old answer keeps playing after interrupt (s)'),
            ('barge_in', 'reply_to_interrupt_s', 'reply to interruption starts (s)'),
            ('tool', 'tool_called', 'capture_lead called'),
            ('tool', 'latency_s', 'tool call latency (s)'),
            ('tool', 'name_ok', 'name captured right'),
            ('tool', 'phone_ok', 'phone captured right')):
        rows.append((label, *(get(p, scenario, key) for p in all_results)))
    width = max(len(r[0]) for r in rows)
    return '\n'.join(f'{r[0]:<{width}}  ' + '  '.join(f'{c:>16}' for c in r[1:]) for r in rows)


# --- entry points ----------------------------------------------------------------------------------

def live_connect_for(provider: str):
    from app.config import get_settings
    settings = get_settings()
    return lambda p: asterisk_bridge.provider_connection(settings, p)


async def main_async(args) -> int:
    if args.selftest:
        from fake_realtime import FakeRealtimeServer  # noqa: WPS433 (local test helper)
        async with FakeRealtimeServer() as fake:
            def connect(provider):
                import websockets
                return websockets.connect(fake.url(provider), open_timeout=5)
            results = {p: await run_provider(p, connect, lambda k: tone(SELFTEST_SECONDS[k]))
                       for p in ('openai_realtime', 'gemini_live')}
    else:
        if not args.yes_spend:
            print('Refusing: --live spends money on provider usage. Re-run with --yes-spend.', file=sys.stderr)
            return 2
        need = {'openai_realtime': 'OPENAI_API_KEY', 'gemini_live': 'GEMINI_API_KEY'}
        missing = [need[p] for p in args.live if not os.environ.get(need[p])]
        if missing:
            print('Missing environment: ' + ', '.join(missing), file=sys.stderr)
            return 2
        cache = Path(tempfile.mkdtemp(prefix='voice-ab-'))
        voice = lambda key: spoken(PHRASES[key], cache)  # noqa: E731
        connect = live_connect_for('')
        results = {}
        for provider in args.live:
            print(f'--- {provider} ---', flush=True)
            results[provider] = await run_provider(provider, connect, voice, args.only)
    print(table(results))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=str))
        print('full results:', args.json)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--live', nargs='+', choices=['openai_realtime', 'gemini_live'])
    parser.add_argument('--yes-spend', action='store_true', help='confirm that live runs cost money')
    parser.add_argument('--only', nargs='+', choices=[n for n, _ in SCENARIOS])
    parser.add_argument('--json', help='write full results to this file')
    args = parser.parse_args()
    if not args.selftest and not args.live:
        parser.error('choose --selftest or --live PROVIDER...')
    return asyncio.run(main_async(args))


if __name__ == '__main__':
    sys.exit(main())
