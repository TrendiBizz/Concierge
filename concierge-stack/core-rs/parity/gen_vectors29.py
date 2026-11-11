"""Batch-29 golden vectors: `asterisk_bridge.MediaBridge` (the Grok event handler, the playback pacer and the AudioSocket
input rules). No network, no database, no telephone call.

Every expected value comes from the LIVE class in `api/app/asterisk_bridge.py`:
 - `grok`: the real `MediaBridge.grok()` coroutine consumes scripted websocket messages from a fake socket. Everything it
   sends, every transcript/tool callback and the shared state after each message are recorded in order.
 - `output`: the real `MediaBridge.output()` coroutine runs against a virtual clock (the module's `asyncio.sleep` and loop
   time are replaced), so each 20 ms tick, each frame written and the end-of-call linger are exact and repeatable.
 - `input`: the real `MediaBridge.input()` coroutine reads pre-fed AudioSocket byte streams from a real `StreamReader`.
 - `b64`: the real `base64.b64decode(text, validate=True)` call the handler uses for audio deltas.
`"declined": N` marks a scenario whose message N the Rust port must REFUSE (fail closed) instead of reproducing: Python
accepts NaN/Infinity literals, lone surrogates and non-string identifiers there. The port may refuse; it must never differ.

    cd api && python -I ../concierge-stack/core-rs/parity/gen_vectors29.py > ../concierge-stack/core-rs/parity/vectors29.json
"""
import asyncio
import base64
import binascii
import datetime
import hashlib
import json
import random
import struct
import sys
from unittest.mock import patch

sys.path.insert(0, "../QA/verification/shims")
sys.path.insert(0, ".")
from app import asterisk_bridge as pbx  # noqa: E402

TRANSCRIPTS = ("conversation.item.input_audio_transcription.completed", "response.output_audio_transcript.done",
               "response.audio_transcript.done")
DELTAS = ("response.output_audio.delta", "response.audio.delta")
TOOL = "response.function_call_arguments.done"
TOOL_RESULTS = [
    {"ok": True}, {"ok": False, "error": "Nope — café"}, {"business": "alpha"}, "plain string", None, 5,
    {"items": [1, 2.5, {"a": None}], "when": datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.timezone.utc)},
    {"nested": {"emoji": "\U0001f600", "quote": "say \"hi\"", "list": []}},
]


def classify(error):
    """A coarse, stable name for what Python raised (the bridge itself only logs the type name)."""
    name, text = type(error).__name__, str(error)
    if isinstance(error, json.JSONDecodeError):
        return "json"
    if isinstance(error, asyncio.IncompleteReadError):
        return "incomplete"
    if isinstance(error, binascii.Error) or text == "string argument should contain only ASCII characters":
        return "base64"
    if isinstance(error, AttributeError):
        return "not_object"
    if isinstance(error, KeyError):
        return "key"
    if isinstance(error, TypeError):
        return "type"
    if isinstance(error, ValueError):
        return "value:" + text
    if isinstance(error, RuntimeError):
        return "runtime:" + text
    return "other:" + name


def expand(message):
    """Vector messages are raw websocket text, or a compact `{"zeros": n, "type": kind}` standing for n zero bytes of audio."""
    if isinstance(message, dict):
        return json.dumps({"type": message["type"], "delta": base64.b64encode(b"\0" * message["zeros"]).decode()})
    return message


def state(bridge):
    return {
        "playback_len": len(bridge.playback),
        "playback_sha256": hashlib.sha256(bytes(bridge.playback)).hexdigest(),
        "ready": bridge.ready.is_set(),
        "ending": bridge.ending,
        "speaking": bridge.speaking,
        "pending": [[ident, json.dumps(result, default=str)] for ident, result in bridge.pending],
    }


async def run_grok(session, messages):
    log, steps, results = [], [], iter(range(10 ** 6))

    class Socket:
        def __init__(self):
            self.index = 0

        async def send(self, text):
            log.append({"send": json.loads(text)})

        def __aiter__(self):
            return self

        async def __anext__(self):
            steps.append({"log": list(log), "state": state(bridge)})
            log.clear()
            if self.index >= len(messages):
                raise StopAsyncIteration
            self.index += 1
            return expand(messages[self.index - 1])

    async def transcript(role, text, item_id):
        log.append({"transcript": [role, text, item_id if item_id else None]})

    async def tool(name, args):
        result = TOOL_RESULTS[next(results) % len(TOOL_RESULTS)]
        log.append({"tool": [name, args], "output": json.dumps(result, default=str)})
        return result

    bridge = pbx.MediaBridge(None, None, Socket(), session, transcript, tool)
    out = {"session": session, "messages": messages, "steps": steps}
    try:
        await bridge.grok()
        out["end"] = "closed"
    except Exception as error:  # noqa: BLE001 - the vector records whatever Python raised
        out["end"] = classify(error)
        out["partial"] = list(log)
    return out


def ev(kind, **fields):
    return json.dumps({"type": kind, **fields}, ensure_ascii=False)


def audio(rng, samples):
    return base64.b64encode(bytes(rng.randrange(256) for _ in range(samples * 2))).decode()


def random_event(rng):
    roll = rng.randrange(100)
    ids = ["a", "b", "éé", "", None]
    if roll < 6:
        return ev("session.updated")
    if roll < 16:
        return ev("response.created")
    if roll < 30:
        return ev("response.done")
    if roll < 40:
        return ev("input_audio_buffer.speech_started")
    if roll < 55:
        return ev(rng.choice(DELTAS), delta=audio(rng, rng.randrange(0, 40)))
    if roll < 78:
        fields = {}
        if rng.random() < .8:
            fields["item_id"] = rng.choice(ids)
        if rng.random() < .5:
            fields["response_id"] = rng.choice(ids)
        if rng.random() < .95:
            fields["transcript"] = rng.choice(["hello", "hello there", "hello there, café", "", None, 5, ["x"], "bye"])
        return ev(rng.choice(TRANSCRIPTS), **fields)
    if roll < 95:
        fields = {}
        if rng.random() < .95:
            fields["call_id"] = rng.choice(["t1", "t2", "t3", "t4", "t5", "", None, 7, "x" * 200, "x" * 201, "é" * 200])
        if rng.random() < .9:
            fields["name"] = rng.choice(["search_knowledge", "end_call", "book_appointment", "", None, 5])
        if rng.random() < .8:
            fields["arguments"] = rng.choice(["{}", '{"a": 1}', '{"q": "caf\\u00e9", "n": [1, 2.5, null], "deep": {"k": true}}',
                                             ' {"dup": 1, "dup": 2} '])
        return ev(TOOL, **fields)
    return rng.choice([ev("something.else", delta="!!"), json.dumps({"no_type": True}), json.dumps({"type": 5}),
                       json.dumps({"type": None}), json.dumps({"type": ["response.done"]}), "{}"])


def grok_scenarios():
    rng = random.Random(20261111)
    session = {"instructions": "alpha", "audio": {"input": {"format": {"type": "audio/pcm", "rate": 8000}}},
               "tools": [{"type": "function", "name": "end_call"}], "turn_detection": {"threshold": 0.5}}
    prefix = [ev("session.updated"), ev("response.created")]
    tool = lambda ident, name="search_knowledge", **more: ev(TOOL, call_id=ident, name=name, **more)  # noqa: E731
    said = lambda kind, text, **more: ev(kind, transcript=text, **more)  # noqa: E731
    fixed = [
        [],
        [ev("session.updated"), ev("session.updated")],
        # the existing pytest's conversation: cumulative transcript, one tool round trip, barge-in
        prefix + [ev(DELTAS[0], delta=base64.b64encode(bytes([1, 0]) * 160).decode()),
                  said(TRANSCRIPTS[0], "alpha enquiry", item_id="same-id"), said(TRANSCRIPTS[0], "alpha enquiry", item_id="same-id"),
                  said(TRANSCRIPTS[0], "alpha enquiry complete", item_id="same-id"), tool("same-tool-id", arguments="{}"),
                  ev("response.done"), ev("response.created"), ev("input_audio_buffer.speech_started")],
        # barge-in while silent sends no cancel; it still flushes playback and withdraws a pending end
        [ev("session.updated"), ev(DELTAS[1], delta=audio(rng, 100)), ev("input_audio_buffer.speech_started"),
         ev("response.created"), tool("e1", "end_call"), ev("input_audio_buffer.speech_started"), ev("response.done")],
        # end_call: result is queued, and no new response is requested afterwards
        prefix + [tool("e1", "end_call", arguments="{}"), ev("response.done"), ev("response.done")],
        prefix + [tool("t1"), tool("e1", "end_call"), tool("t2"), ev("response.done")],
        # several tool results flushed in order, then one response.create
        prefix + [tool("t1"), tool("t2", "book_appointment", arguments='{"when": "tomorrow"}'), tool("t1"), tool("t3"),
                  ev("response.done"), ev("response.done")],
        # same item id, different roles are different turns; same text again is dropped; a new text replaces
        prefix + [said(TRANSCRIPTS[0], "one", item_id="x"), said(TRANSCRIPTS[1], "one", item_id="x"),
                  said(TRANSCRIPTS[2], "one", item_id="x"), said(TRANSCRIPTS[1], "two", item_id="x"),
                  said(TRANSCRIPTS[0], "one", item_id="x"), said(TRANSCRIPTS[0], "two", item_id="x"),
                  said(TRANSCRIPTS[0], "one", item_id="x")],
        # no identity: every event is a new message; response_id is the fallback identity
        prefix + [said(TRANSCRIPTS[0], "same"), said(TRANSCRIPTS[0], "same"), said(TRANSCRIPTS[1], "r", response_id="r1"),
                  said(TRANSCRIPTS[1], "r", response_id="r1"), said(TRANSCRIPTS[1], "r", item_id="", response_id="r1"),
                  said(TRANSCRIPTS[1], "r", item_id=None, response_id="r2"), said(TRANSCRIPTS[1], "r", item_id=0, response_id="r2"),
                  said(TRANSCRIPTS[1], "s", item_id=False, response_id=""), said(TRANSCRIPTS[1], "s", item_id=[], response_id=None),
                  said(TRANSCRIPTS[1], "s", item_id={}, response_id=0), said(TRANSCRIPTS[1], "s", item_id="i", response_id="r1"),
                  said(TRANSCRIPTS[1], "s", item_id="i", response_id="r2")],
        # a non-string identity with no usable text is a no-op in Python, so the port must not refuse it
        prefix + [said(TRANSCRIPTS[0], "", item_id=5), said(TRANSCRIPTS[0], None, item_id=[1]), said(TRANSCRIPTS[0], 7, item_id=True),
                  ev(TRANSCRIPTS[0], item_id={"a": 1}), said(TRANSCRIPTS[0], "kept", item_id="ok")],
        # transcript longer than 10,000 characters is cut by code point, and compared uncut
        prefix + [said(TRANSCRIPTS[0], "é" * 10001, item_id="long"), said(TRANSCRIPTS[0], "é" * 10001, item_id="long"),
                  said(TRANSCRIPTS[0], "é" * 10002, item_id="long"), said(TRANSCRIPTS[1], "\U0001f600" * 10001, item_id="long")],
        # ignored tool calls: bad, empty, over-long and repeated identifiers
        prefix + [tool(""), tool(None), tool(7), tool("x" * 201), tool("é" * 200), tool("é" * 201), ev(TOOL, name="n"),
                  tool("é" * 200), ev(TOOL, call_id="noname"), tool("numname", 5), ev("response.done")],
        # exactly 40 tools is allowed
        prefix + [tool(f"t{i}") for i in range(40)] + [tool("t3"), ev("response.done")],
        # playback bound: exactly 30 s is allowed, cleared by barge-in, then refilled
        [{"zeros": 240000, "type": DELTAS[0]}, {"zeros": 240000, "type": DELTAS[1]}, ev("input_audio_buffer.speech_started"),
         {"zeros": 479998, "type": DELTAS[0]}, ev(DELTAS[0], delta="AAA="), ev(DELTAS[0], delta="")],
        [ev(DELTAS[0], delta="QR=="[:2] + "A="), ev(DELTAS[0], delta="AAAA"[:0])],
        # tolerated oddities: duplicate keys (last wins), huge integers in ignored fields, stray whitespace
        ['{"type": "response.created", "type": "response.done"}', ' {"type": "response.created", "n": 123456789012345678901234567890}\n',
         '{"type": "response.done", "f": 1.5e3, "g": -0.0}', ev("response.created"), ev("input_audio_buffer.speech_started")],
    ]
    failing = [
        "not json", "", "[]", '"text"', "5", "null", "true", '{"type": "response.created"', "﻿{}",
        ev("error"), ev("error", error={"message": "bad"}),
        ev(DELTAS[0]), ev(DELTAS[1], delta=5), ev(DELTAS[0], delta=None), ev(DELTAS[0], delta=["QUJD"]), ev(DELTAS[0], delta="QQ="),
        ev(DELTAS[0], delta="QQ=="), ev(DELTAS[1], delta="QUJD"), ev(DELTAS[0], delta="QUJD\n"), ev(DELTAS[0], delta="éééé"),
        ev(DELTAS[0], delta="QUJDRA==QUJDRA=="), ev(DELTAS[0], delta="-_-_"),
        tool("bad", arguments="[]"), tool("bad", arguments="5"), tool("bad", arguments="null"), tool("bad", arguments='"{}"'),
        tool("bad", arguments="nope"), tool("bad", arguments=""), tool("bad", arguments=5), tool("bad", arguments=None),
        tool("bad", arguments={}), tool("bad", "end_call", arguments="[]"),
    ]
    scenarios = fixed + [prefix + [ev(DELTAS[0], delta=audio(rng, 8)), bad, ev("response.done")] for bad in failing]
    scenarios.append(prefix + [tool(f"t{i}") for i in range(41)] + [ev("response.done")])
    scenarios.append([{"zeros": 240000, "type": DELTAS[0]}, {"zeros": 240000, "type": DELTAS[0]}, {"zeros": 2, "type": DELTAS[0]}])
    scenarios.append([{"zeros": 479998, "type": DELTAS[0]}, ev(DELTAS[1], delta=audio(rng, 2))])
    # a repeated identifier after its first failure is still "seen" - reachable only before the raise, kept for the record
    for _ in range(140):
        scenarios.append([random_event(rng) for _ in range(rng.randrange(1, 60))])
    declined = [
        '{"type": "response.created", "v": NaN}', '{"type": "response.created", "v": Infinity}', '{"type": "response.created", "v": -Infinity}',
        '{"type": "response.created", "v": 1e999}', '{"type": "response.created", "v": "\\ud800"}',
        tool("nan", arguments='{"a": NaN}'), tool("sur", arguments='{"a": "\\udfff"}'),
        said(TRANSCRIPTS[0], "text", item_id=5), said(TRANSCRIPTS[0], "text", item_id=True), said(TRANSCRIPTS[1], "text", item_id=1.5),
        said(TRANSCRIPTS[0], "text", item_id=[1]), said(TRANSCRIPTS[0], "text", item_id={"a": 1}),
        said(TRANSCRIPTS[2], "text", item_id="", response_id=9), said(TRANSCRIPTS[2], "text", response_id=["r"]),
    ]
    out = [asyncio.run(run_grok(session, s)) for s in scenarios]
    for bad in declined:
        messages = prefix + [said(TRANSCRIPTS[0], "before", item_id="k"), bad, ev("response.done")]
        case = asyncio.run(run_grok(session, messages))
        # Keep only what happened BEFORE the refused message: what Python did with it (NaN, a lone surrogate) is not
        # valid JSON for the vector file, and the port makes no claim about it.
        out.append({"session": session, "messages": messages, "steps": case["steps"][:4], "end": None, "declined": 3})
    return out


# ---- output pacer ---------------------------------------------------------------------------------------------------
class Stop(Exception):
    pass


def run_output(start, init, ops, limit):
    """`ops[k]` are applied after tick k (during its sleep); `init` before the first tick."""
    clock = {"now": start}
    ticks, awaiting = [], [True]

    class Writer:
        def write(self, data):
            kind, length = struct.unpack("!BH", data[:3])
            assert kind == 0x10 and length == len(data) - 3
            ticks[-1]["frame"] = data[3:].hex()

        async def drain(self):
            clock["now"] += ticks[-1]["delay"]

    class Loop:
        def time(self):
            if awaiting[0]:
                awaiting[0] = False
                ticks.append({"now": clock["now"], "frame": None, "delay": 0.0})
            return clock["now"]

    bridge = pbx.MediaBridge(None, Writer(), None, {}, None, None)

    def apply(batch):
        for op, value in batch:
            if op == "extend":
                bridge.playback.extend(bytes.fromhex(value))
            elif op == "clear":
                bridge.playback.clear()
            elif op == "delay":
                pending_delay[0] = value
            else:
                setattr(bridge, op, value)

    pending_delay = [0.0]

    async def sleep(seconds):
        ticks[-1]["slept"] = seconds
        clock["now"] += seconds
        if len(ticks) >= limit:
            raise Stop
        apply(ops[len(ticks) - 1] if len(ticks) - 1 < len(ops) else [])
        awaiting[0] = True

    original_time = Loop.time

    def time(self):
        fresh = awaiting[0]
        value = original_time(self)
        if fresh:
            ticks[-1]["delay"], pending_delay[0] = pending_delay[0], 0.0
        return value

    Loop.time = time
    apply(init)
    finished = False
    with patch.object(pbx.asyncio, "sleep", sleep), patch.object(pbx.asyncio, "get_running_loop", lambda: Loop()):
        coroutine = bridge.output()
        try:
            coroutine.send(None)
            raise AssertionError("output() suspended under a virtual clock")
        except StopIteration:
            finished = True
        except Stop:
            coroutine.close()
    # Clock values travel as IEEE-754 bit patterns: the 0.4 s linger is decided on exact doubles, and a JSON float
    # parser that is one unit in the last place off would move the boundary.
    bits = lambda value: struct.pack(">d", value).hex()  # noqa: E731
    return {"init": init, "ops": ops, "finished": finished, "left": len(bridge.playback),
            "ticks": [{"now": bits(t["now"]), "frame": t["frame"], "slept": bits(t["slept"]) if "slept" in t else None,
                       "after_write": bits(t["now"] + t["delay"] if t["frame"] is not None else t["now"])} for t in ticks]}


def output_scenarios():
    rng = random.Random(20261112)
    pcm = lambda n: bytes(rng.randrange(1, 256) for _ in range(n)).hex()  # noqa: E731
    cases = [
        run_output(0.0, [("ending", True)], [], 60),
        run_output(1000.0, [("ending", True)], [], 60),
        run_output(1000.0, [("ending", True), ("speaking", True)], [[]] * 30 + [[("speaking", False)]], 80),
        run_output(5.5, [("extend", pcm(320 * 3 + 7)), ("ending", True)], [], 60),
        run_output(5.5, [("extend", pcm(1))], [[("extend", pcm(319))], [("extend", pcm(321))]], 12),
        # the linger restarts after audio, but NOT after a withdrawn end: `idle_since` survives (kept as Python does it)
        run_output(7.25, [("ending", True)], [[]] * 9 + [[("ending", False)]] + [[]] * 30 + [[("ending", True)]], 80),
        run_output(7.25, [("ending", True)], [[]] * 9 + [[("extend", pcm(640))]], 80),
        run_output(3.0, [("ending", True)], [[]] * 18 + [[("speaking", True)]] + [[]] * 5 + [[("speaking", False)]], 80),
        # a slow socket write shortens (or removes) the following sleep
        run_output(2.0, [("extend", pcm(320 * 6)), ("ending", True), ("delay", 0.005)],
                   [[("delay", 0.02)], [("delay", 0.05)], [("delay", 0.0199)], []], 60),
        run_output(0.0, [], [], 10),
    ]
    # The linger is `>= 0.4`: find clocks whose 20 ms steps land on a difference of EXACTLY 0.4, so that `>` would differ.
    exact = []
    # (Rounding in the twenty additions makes this rare: it happens for a few clocks just above zero.)
    for start in [n / 1000000 for n in range(5000, 10000)]:
        now = start
        for _ in range(20):
            now += .02
        if now - start == .4:
            exact.append(start)
    assert len(exact) >= 5, exact
    for start in exact[:5]:
        case = run_output(start, [("ending", True)], [], 60)
        assert case["finished"] and len(case["ticks"]) == 21, (start, len(case["ticks"]))
        cases.append(case)
    for _ in range(60):
        ops = []
        for _ in range(rng.randrange(5, 90)):
            batch = []
            roll = rng.random()
            if roll < .25:
                batch.append(("extend", pcm(rng.choice([1, 2, 319, 320, 321, 640, 700, rng.randrange(1, 1500)]))))
            if rng.random() < .08:
                batch.append(("clear", True))
            if rng.random() < .12:
                batch.append(("ending", rng.random() < .7))
            if rng.random() < .12:
                batch.append(("speaking", rng.random() < .4))
            if rng.random() < .1:
                batch.append(("delay", rng.choice([0.001, 0.01, 0.02, 0.03])))
            ops.append(batch)
        cases.append(run_output(rng.choice([0.0, 0.02, 1.0, 86400.5, 12345.678]), [("ending", rng.random() < .5)], ops, 140))
    return cases


# ---- input rules ----------------------------------------------------------------------------------------------------
def frame(kind, body=b""):
    return struct.pack("!BH", kind, len(body)) + body


async def run_input(stream):
    sent = []

    class Socket:
        async def send(self, text):
            event = json.loads(text)
            assert set(event) == {"type", "audio"} and event["type"] == "input_audio_buffer.append"
            sent.append(base64.b64decode(event["audio"]).hex())

    reader = asyncio.StreamReader()
    reader.feed_data(stream)
    reader.feed_eof()
    bridge = pbx.MediaBridge(reader, None, Socket(), {}, None, None)
    bridge.ready.set()
    try:
        await bridge.input()
        end = "hangup"
    except Exception as error:  # noqa: BLE001
        end = classify(error)
    # No scripted body is 320 zero bytes, so any such frame would be VAD silence injected by a stalled machine.
    assert (b"\0" * pbx.FRAME_BYTES).hex() not in sent, "timing stall while generating: run again"
    return {"stream": stream.hex(), "sent": sent, "end": end}


def input_scenarios():
    rng = random.Random(20261113)
    pcm = lambda n: bytes(rng.randrange(1, 256) for _ in range(n))  # noqa: E731
    hang = frame(0)
    streams = [
        b"", hang, frame(0, b"bye") + frame(0x10, pcm(2)), frame(0x10, pcm(320)) + hang, frame(0x10, pcm(2)) + frame(0x10, pcm(8192)) + hang,
        frame(0x10, pcm(320)), frame(0x10, pcm(320))[:100], frame(0x10, pcm(320)) + b"\x10", frame(0x10, pcm(320)) + b"\x10\x01",
        frame(0x10) + hang, frame(0x10, pcm(1)) + hang, frame(0x10, pcm(321)) + hang, frame(0x10, pcm(4)) + frame(0x10, pcm(3)) + hang,
        frame(3, b"5") + frame(0x10, pcm(4)) + frame(3, b"#") + hang, frame(3) + hang, frame(3, b"12") + hang,
        frame(1, pcm(16)) + hang, frame(2, b"x") + hang, frame(0xFF, b"\x01") + hang, frame(0x11, pcm(2)) + hang,
        struct.pack("!BH", 0x10, 8193), struct.pack("!BH", 0x10, 8193) + pcm(8193) + hang, struct.pack("!BH", 0, 65535),
        frame(0x10, pcm(2)) + struct.pack("!BH", 3, 9000) + hang, struct.pack("!BH", 0x10, 8192) + pcm(10),
    ]
    for _ in range(60):
        parts = []
        for _ in range(rng.randrange(1, 9)):
            roll = rng.random()
            if roll < .6:
                parts.append(frame(0x10, pcm(2 * rng.randrange(1, 200))))
            elif roll < .75:
                parts.append(frame(3, pcm(1)))
            elif roll < .85:
                parts.append(hang)
            elif roll < .93:
                parts.append(frame(rng.choice([1, 2, 3, 0x10, 0x11, 0xFF]), pcm(rng.randrange(0, 5))))
            else:
                parts.append(frame(0x10, pcm(40))[:rng.randrange(1, 43)])
        streams.append(b"".join(parts))
    return [asyncio.run(run_input(s)) for s in streams]


def b64_cases():
    rng = random.Random(20261114)
    texts = ["", "QQ==", "QR==", "QQ=", "QQ", "Q", "QUI=", "QUJ=", "QUJD", "QUJD=", "QUJD==", "QUJDRA==", "QUJDRA=", "QUJDRA", "====",
             "=QQ=", "Q=Q=", "QQ==QQ==", "QUJDRA==x", "QUJD\n", " QUJD", "QUJD ", "QU JD", "Q-_/", "QUJ+", "QUJ/", "éééé",
             "QUJDé", "QQ==\n", "QUJDQUJDQUJD", "A" * 400, "/" * 4, "+" * 8]
    for _ in range(500):
        texts.append("".join(rng.choice("QUJDRAaz09+/=") if rng.random() < .97 else rng.choice(" \n-_!") for _ in range(rng.randrange(0, 13))))
    out = []
    for text in texts:
        try:
            out.append({"text": text, "hex": base64.b64decode(text, validate=True).hex()})
        except Exception as error:  # noqa: BLE001
            assert classify(error) == "base64", (text, error)
            out.append({"text": text, "hex": None})
    return out


print(json.dumps({"grok": grok_scenarios(), "output": output_scenarios(), "input": input_scenarios(), "b64": b64_cases()},
                 ensure_ascii=False, indent=None, separators=(",", ":")))
