"""Batch-19 golden vectors: `phone_relay` decision flows from the live module (inbound registration, setup, consented recording start,
recording callback, call finish and the relay session state machine) with fake database, provider and WebSocket.
No call is made and no recording is started.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors19.py > ../concierge-stack/core-rs/parity/vectors19.json
"""
import asyncio
import json
import random
import sys
from types import SimpleNamespace

import httpx
from fastapi import WebSocketDisconnect

sys.path.insert(0, ".")
from app import channel_authorization, chat, convo, db, enquiries, phone_relay as pr, tenants  # noqa: E402

rng = random.Random(20261126)
out = {}


class CM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


def settings(**k):
    base = dict(phone_voice_provider="legacy_twilio_tts", phone_receptionist_enabled=True, twilio_auth_token="tok", public_base_url="https://c.example.com",
                phone_recording_enabled=True, twilio_account_sid="AC" + "0" * 32)
    base.update(k)
    return SimpleNamespace(**base)


SIDS = ["CA" + "a" * 32, "CA" + "A" * 32, "CA" + "a" * 31, "ca" + "a" * 32, "CA" + "g" * 32, "", "CA" + "a" * 32 + "\n"]
NUMS = ["+64211234567", "+6421123", "+0211234567", "64211234567", "", "+" + "1" * 15, "+" + "1" * 16]


def pick_cfg(p=0.75):
    return settings() if rng.random() < p else rng.choice(cfg_variants())


def pick(opts, p=0.85):
    return opts[0] if rng.random() < p else rng.choice(opts)


def cfg_variants():
    return [settings(), settings(phone_voice_provider="grok"), settings(phone_receptionist_enabled=False), settings(twilio_auth_token=""), settings(public_base_url="http://c.example.com"),
            settings(phone_recording_enabled=False), settings(twilio_account_sid=""), settings(twilio_account_sid="AC" + "0" * 31), settings(twilio_account_sid="XX" + "0" * 32)]


# ---- register_inbound ----------------------------------------------------------------------------------------------------
reg = []
for _ in range(400):
    cfg = pick_cfg()
    params = {}
    for k, opts in (("CallSid", SIDS), ("To", NUMS), ("From", NUMS + ["+1" + "2" * 40, "anonymous"])):
        if rng.random() < 0.97:
            params[k] = pick(opts)
    row = rng.choice([None, {"id": "t-1", "phone_daily_limit": rng.choice([0, 1, 5, 9]), "name": "Acme", "slug": "acme"}, {"id": "t-1", "phone_daily_limit": rng.choice([5, 9]), "name": "Acme", "slug": "acme"}])
    auth = {"telephone": rng.choice([True, True, True, False]), "call_recording": rng.choice([True, False])}
    previous = rng.choice([None, {"tenant_id": "t-1"}, {"tenant_id": "other"}])
    used = rng.choice([0, 1, 4, 5, 9])
    effects = []

    class Conn:
        def transaction(self):
            return CM()

        async def execute(self, sql, *a):
            effects.append(["execute", sql.split("(")[0].strip()[:40], list(a)])

        async def fetchrow(self, sql, *a):
            effects.append(["fetchrow", sql.strip()[:30], list(a)])
            return previous

        async def fetchval(self, sql, *a):
            effects.append(["fetchval", sql.strip()[:30], list(a)])
            return used

    class Pool:
        def acquire(self):
            return CM(Conn())

        async def fetchrow(self, sql, *a):
            effects.append(["tenant_lookup", list(a)])
            return row

    async def is_auth(tid, ch):
        effects.append(["authorized", [tid, ch]])
        return auth[ch]

    async def goc(t, session, ch, page, utm):
        effects.append(["get_or_create", [t["id"], session, ch, page, utm]])
        return "conv-1"

    async def cap(t, ch, source, msg, **kw):
        effects.append(["capture", [t["id"], ch, source, msg, kw]])

    db.pool = lambda: Pool()
    channel_authorization.is_authorized = is_auth
    convo.get_or_create, enquiries.capture = goc, cap
    pr.get_settings = lambda cfg=cfg: cfg
    try:
        res = {"ok": asyncio.run(pr.register_inbound(params))}
    except pr.PhoneError as e:
        res = {"err": str(e)}
    reg.append({"cfg": vars(cfg), "params": params, "row": row, "auth": auth, "previous": previous, "used": used, "out": res, "effects": effects})
out["register"] = reg

# ---- finish / recording callback --------------------------------------------------------------------------------------------
fin, cb = [], []
for sid in SIDS:
    for status in ["completed", "relay_ended", "x" * 60, ""]:
        eff = []

        class P1:
            async def execute(self, sql, *a):
                eff.append(list(a))

        db.pool = lambda: P1()
        asyncio.run(pr.finish(sid, status))
        fin.append({"sid": sid, "status": status, "effects": eff})
RECS = ["RE" + "a" * 32, "RE" + "g" * 32, "re" + "a" * 32, "", "RE" + "a" * 31]
for sid in SIDS[:3] + [""]:
    for rec in RECS:
        for status in ["in-progress", "completed", "absent", "failed", "queued", "", "COMPLETED"]:
            params = {"CallSid": sid, "RecordingSid": rec, "RecordingStatus": status}
            if rng.random() < 0.1:
                params.pop("RecordingStatus")
            eff = []

            class P2:
                async def execute(self, sql, *a):
                    eff.append(list(a))

            db.pool = lambda: P2()
            try:
                asyncio.run(pr.recording_callback(params))
                r = {"ok": True}
            except pr.PhoneError as e:
                r = {"err": str(e)}
            cb.append({"params": params, "out": r, "effects": eff})
out["finish"], out["callback"] = fin, cb

# ---- _record_setup ----------------------------------------------------------------------------------------------------------
setup = []
for _ in range(300):
    cfg = pick_cfg()
    data = {}
    for k, opts in (("callSid", SIDS), ("sessionId", ["sess-1", "", 5, "s" * 150, None]), ("to", NUMS), ("from", NUMS + [None])):
        if rng.random() < 0.97:
            data[k] = pick(opts)
    row = rng.choice([None, {"to_number": data.get("to", "+64211234567"), "from_number": data.get("from") or "", "tenant_id": "t-1"}, {"to_number": data.get("to", "+64211234567"), "from_number": data.get("from") or "", "tenant_id": "t-1"}, {"to_number": data.get("to", "+64211234567"), "from_number": "", "tenant_id": "t-1"},
                      {"to_number": "+64211234567", "from_number": "+64299999999", "tenant_id": "t-1"}, {"to_number": data.get("to"), "from_number": "+64211111111", "tenant_id": "t-1"}])
    tenant = rng.choice([None, {"id": "t-1", "name": "Acme"}, {"id": "t-1", "name": "Acme"}, {"id": "t-1", "name": "Acme"}])
    auth = rng.choice([True, False])
    eff = []

    class P3:
        async def fetchrow(self, sql, *a):
            eff.append(["fetchrow", list(a)])
            return row

        async def execute(self, sql, *a):
            eff.append(["execute", list(a)])

    async def gbi(tid, tenant=tenant):
        eff.append(["get_by_id", [tid]])
        return dict(tenant) if tenant else None

    async def is_auth2(tid, ch, auth=auth):
        eff.append(["authorized", [tid, ch]])
        return auth

    db.pool = lambda: P3()
    tenants.get_by_id = gbi
    channel_authorization.is_authorized = is_auth2
    pr.get_settings = lambda cfg=cfg: cfg
    r = asyncio.run(pr._record_setup(data))
    setup.append({"cfg": vars(cfg), "data": data, "row": row, "tenant": tenant, "auth": auth, "out": r, "effects": eff})
out["setup"] = setup

# ---- begin_recording ----------------------------------------------------------------------------------------------------------
rec = []
for _ in range(300):
    cfg = pick_cfg(0.8)
    sid = pick(SIDS, 0.9)
    auth = rng.choice([True, True, True, False])
    updated = rng.choice([None, {"call_sid": "x"}, {"call_sid": "x"}])
    provider = rng.choice([("status", 200, {"sid": "RE" + "a" * 32}), ("status", 201, {"sid": "RE" + "b" * 32}), ("status", 200, {"sid": "bad"}), ("status", 200, {}), ("status", 200, [1]),
                           ("status", 400, {}), ("status", 500, {"sid": "RE" + "a" * 32}), ("status", 200, "INVALID"), ("error",)])
    eff = []

    class P4:
        async def fetchrow(self, sql, *a):
            eff.append(["claim", list(a)])
            return updated

        async def execute(self, sql, *a):
            eff.append(["execute", sql.split("SET")[1].split("WHERE")[0].strip()[:40], list(a)])

    class Resp:
        def __init__(self, st, body):
            self.status_code, self.b = st, body

        def json(self):
            if self.b == "INVALID":
                raise ValueError("x")
            return self.b

    class Client:
        def __init__(self, timeout=None, follow_redirects=None):
            eff.append(["client", [timeout, follow_redirects]])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, url, auth=None, data=None):
            eff.append(["post", [url, list(auth), data]])
            if provider[0] == "error":
                raise httpx.ConnectError("x")
            return Resp(provider[1], provider[2])

    async def is_auth3(tid, ch, auth=auth):
        eff.append(["authorized", [tid, ch]])
        return auth

    db.pool = lambda: P4()
    pr.httpx.AsyncClient = Client
    channel_authorization.is_authorized = is_auth3
    pr.get_settings = lambda cfg=cfg: cfg
    try:
        r = {"ok": asyncio.run(pr.begin_recording(sid, {"id": "t-1"}))}
    except Exception as e:  # noqa: BLE001
        r = {"raises": type(e).__name__}
    rec.append({"cfg": vars(cfg), "sid": sid, "auth": auth, "updated": updated, "provider": provider, "out": r, "effects": eff})
out["recording"] = rec

# ---- relay session state machine ------------------------------------------------------------------------------------------------
async def fast(_):
    return None


relay = []
SESSION = "CA" + "a" * 32
for case in range(260):
    cfg = pick_cfg(0.92) if case >= 8 else settings()
    sig_ok = rng.random() < 0.93 if case >= 8 else True
    max_seconds = rng.choice([600] * 12 + [0]) if case >= 8 else 600
    setup_event = {"type": "setup", "callSid": SESSION, "sessionId": "s1", "to": "+64211234567", "from": "+64277777777"}
    events = []
    if rng.random() < 0.08:
        events.append({"type": "prompt", "last": True, "voicePrompt": "hello"})
    events.append(setup_event)
    offer = rng.random() < 0.5
    for _ in range(rng.choice([0, 1, 2, 3, 6, 22])):
        k = rng.random()
        if k < 0.65:
            events.append({"type": "prompt", "last": rng.choice([True, True, True, False]), "voicePrompt": rng.choice(
                ["What are your hours?", "", "   ", "I consent to recording", "yes, i consent to this call recording!", "x" * 1500, None, 5, "é"])})
        elif k < 0.8:
            events.append({"type": "interrupt"})
        elif k < 0.9:
            events.append({"type": rng.choice(["error", "info", "dtmf", "weird"]), "code": "c"})
        else:
            events.append({"type": "setup", "callSid": SESSION, "sessionId": "again", "to": "+64211234567", "from": "+64277777777"})
    if case < 8:
        events = [setup_event] + [{"type": "prompt", "last": True, "voicePrompt": "q%d" % i} for i in range(18 + case)]
    row_ok = rng.random() < 0.9
    record_ok = rng.choice([True, True, True, False]) if case >= 8 else True
    run_turn_mode = rng.choice(["ok", "ok", "ok", "empty", "none", "raise"])
    begin_ok = rng.choice([True, False])
    eff = []
    sent = []

    class WS:
        def __init__(self):
            self.headers = {"x-twilio-signature": "sig"}
            self.i = 0

        async def close(self, code=None):
            sent.append(["close", code])

        async def accept(self):
            sent.append(["accept"])

        async def send_json(self, data):
            sent.append(["send", data])

        async def receive_json(self):
            await asyncio.sleep(0.002)
            if self.i >= len(events):
                raise WebSocketDisconnect()
            ev = events[self.i]
            self.i += 1
            return ev

    async def rec_setup(data, record_ok=record_ok, offer=offer):
        eff.append(["record_setup", [data.get("callSid"), data.get("sessionId")]])
        return {"id": "t-1", "name": "Acme", "_recording_offer": offer} if record_ok else None

    async def goc2(t, session, ch, page, utm):
        eff.append(["get_or_create", [session]])
        return "conv-1"

    async def cap2(t, ch, source, msg, **kw):
        eff.append(["capture", [source, msg]])

    async def run_turn(t, session, ch, prompt, sender_phone=None):
        eff.append(["run_turn", [session, ch, prompt]])
        if run_turn_mode == "raise":
            raise RuntimeError("boom")
        if run_turn_mode == "none":
            return {"reply": None}
        if run_turn_mode == "empty":
            return {"reply": "   "}
        return {"reply": "Answer: " + prompt + "y" * 1300}

    async def begin(sid, t, begin_ok=begin_ok):
        eff.append(["begin_recording", [sid]])
        return begin_ok

    async def fin2(sid, status):
        eff.append(["finish", [sid, status]])

    class P5:
        async def execute(self, sql, *a):
            eff.append(["decline", list(a)])

    pr._record_setup, pr.begin_recording, pr.finish = rec_setup, begin, fin2
    convo.get_or_create, enquiries.capture, chat.run_turn = goc2, cap2, run_turn
    pr.chat.run_turn = run_turn
    db.pool = lambda: P5()
    pr.get_settings = lambda cfg=cfg: cfg
    pr.valid_websocket_signature = lambda s, sig_ok=sig_ok: sig_ok
    pr.MAX_SECONDS = max_seconds
    asyncio.run(pr.relay(WS()))
    relay.append({"cfg": vars(cfg), "sig_ok": sig_ok, "max_seconds": max_seconds, "events": events, "offer": offer, "record_ok": record_ok, "mode": run_turn_mode, "begin_ok": begin_ok,
                  "sent": sent, "effects": eff})
out["relay"] = relay
json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
