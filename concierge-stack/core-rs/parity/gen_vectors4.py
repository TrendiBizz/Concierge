"""Batch-4 golden vectors: tool specs, lead-capture normalisation, search query, Twenty payload/URL, views.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors4.py > ../concierge-stack/core-rs/parity/vectors4.json
"""
import asyncio
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import events, tools  # noqa: E402

rng = random.Random(20261112)
UTC = timezone.utc

# ---- tool lists across tenant shapes ---------------------------------------------------------
tool_cases = []
for burl in (None, "", "https://x.test/book"):
    for native in (None, False, True):
        tenant = {"booking_url": burl, "native_booking": native}
        tool_cases.append({"tenant": tenant, "chat": tools.chat_tools(tenant), "voice": tools.voice_tools(tenant),
                           "voice_web": tools.voice_tools(tenant, website=True)})

# ---- capture_lead normalisation (SQL args captured from the live function with a fake pool) ---
captured = []


class FakePool:
    async def fetchrow(self, sql, *a):
        captured.append(a)
        return {"id": 1}


async def _noop(*a, **k):
    return None


tools.db.pool = lambda: FakePool()
tools.automation.on_lead_created = _noop
VALS = ["", "  Ann  ", "Ann Lee", "x" * 150, "é" * 130, "a@b.co", " a@b.co ", "bad", "+64 21 123 4567", "021 123 4567", "5551234567",
        "(555) 123-4567", "12345", "m" * 1200, "line\nbreak", None, True, False, 0, 5, "日本語"]
capture_cases = []
for _ in range(400):
    args = {k: rng.choice(VALS) for k in ("name", "email", "phone", "message") if rng.random() < 0.85}
    for k in ("consent_to_contact", "consent_to_marketing"):
        if rng.random() < 0.7:
            args[k] = rng.choice([True, False, None, 1, 0, "yes", ""])
    sender = rng.choice([None, "", "+6421999888", "021 555 777"])
    sms = rng.choice([True, False])
    cc = rng.choice(["1", "64"])
    tools.get_settings = lambda cc=cc: SimpleNamespace(default_country_code=cc)
    ctx = {"channel": "chat", "sms_inbound": sms}
    if sender is not None:
        ctx["sender_phone"] = sender
    captured.clear()
    res = asyncio.run(tools._capture_lead({"id": "t"}, args, ctx))
    if res.get("ok"):
        a = captured[0]
        out = {"ok": {"name": a[2], "email": a[3], "phone": a[4], "message": a[5], "consent": a[10], "marketing": a[11]}}
    else:
        out = {"err": res["error"]}
    capture_cases.append({"args": args, "sender": sender, "sms": sms, "cc": cc, "out": out})

# ---- search_knowledge query clamp -------------------------------------------------------------
seen = []


async def fake_retrieve(tid, q, k=4):
    seen.append(q)
    return []


tools.retrieve = fake_retrieve
search_cases = []
for q in ["", "  ", "hours", "  padded query  ", "q" * 400, "é" * 301, None, True, 5, 0, False]:
    seen.clear()
    args = {} if q is None else {"query": q}
    res = asyncio.run(tools._search_knowledge({"id": "t"}, args, {}))
    search_cases.append({"args": args, "out": seen[0] if seen else None})

# ---- Twenty payload ---------------------------------------------------------------------------
NAMES = ["", "Ann", "Ann Lee", "  Ann   Marie  Lee ", "日本 語", "x" * 100 + " " + "y" * 100, None, "Dr\tSmith"]
twenty_cases = []
for _ in range(300):
    ev = rng.choice(["lead.created", "appointment.booked", "voice.completed", "other.event"])
    lead = rng.choice([{}, None, {"name": rng.choice(NAMES), "email": rng.choice(["", "a@b.co", " a@b.co "]), "phone": rng.choice(["", "+6421"]),
                                  "message": rng.choice(["", "Hi", "m" * 1500]), "channel": rng.choice([None, "", "sms", "chat"])}])
    appt = rng.choice([{}, None, {"name": rng.choice(NAMES), "email": rng.choice(["", "z@y.co"]), "phone": rng.choice(["", "+6422"]),
                                   "starts_at": "2026-11-10 10:00:00+00:00", "notes": rng.choice(["", "n" * 1500, "bring ID"])}])
    sections = {}
    if lead is not None:
        sections["lead"] = lead
    if appt is not None:
        sections["appointment"] = appt
    tenant = {"name": rng.choice(["Trendi", "Café " * 40, "", None])}
    twenty_cases.append({"tenant": tenant, "event": ev, "sections": sections, "out": events.twenty_bridge_payload(tenant, ev, sections)})

# ---- bridge URL ---------------------------------------------------------------------------------
URLS = ["http://127.0.0.1:4410/lead", "http://localhost:4410/lead", "http://host.docker.internal:4410/lead", "http://twenty-bridge:4410/lead",
        "https://127.0.0.1:4410/lead", "http://127.0.0.1:4411/lead", "http://127.0.0.1/lead", "http://127.0.0.1:4410/leads", "http://127.0.0.1:4410/lead?x=1",
        "http://127.0.0.1:4410/lead#f", "http://u:p@127.0.0.1:4410/lead", "http://u@127.0.0.1:4410/lead", "http://evil.test:4410/lead", "HTTP://LOCALHOST:4410/lead",
        "http://127.0.0.1:4410/lead/", "http://127.0.0.1:4410", "", "not a url", "http://[::1]:4410/lead", "http://127.0.0.1:44100/lead", "http://127.0.0.1:abc/lead"]
url_cases = []
for u in URLS:
    events.get_settings = lambda u=u: SimpleNamespace(twenty_bridge_url=u)
    try:
        out = events._bridge_url() is not None
    except ValueError:
        out = False
    url_cases.append({"url": u, "ok": out})

# ---- delivery id (mirror of the inline expression in events.process_twenty_once) ----------------
delivery_cases = []
for tid, ev, src in [("0a3e7155-2f19-4527-bee1-f2dec7b676c7", "lead.created", "lead-1"), ("t", "appointment.booked", "é日本😀"), ("t", "voice.completed", 'q"uo\\te\n'),
                     ("", "", ""), ("x" * 40, "lead.created", "\u007f\u0080 "), ("t", "e", "\x00\x1f")]:
    identity = json.dumps([str(tid), ev, str(src)], ensure_ascii=True, separators=(",", ":"))
    delivery_cases.append({"tenant": tid, "event": ev, "source": src, "out": hashlib.sha256(identity.encode("utf-8")).hexdigest()})

# ---- views ----------------------------------------------------------------------------------------
view_cases = []
for _ in range(80):
    secs = rng.randint(1_700_000_000, 1_900_000_000)
    micros = rng.choice([0, 0, 123456, 1, 999999])
    dt = datetime.fromtimestamp(secs, UTC).replace(microsecond=micros)
    lead = {"id": rng.choice(["abc", 7]), "name": rng.choice(["Ann", None, ""]), "email": "a@b.co", "phone": None, "message": "hi", "channel": "chat",
            "score": rng.choice([None, 0, 85]), "score_label": rng.choice([None, "hot"]), "created_at": dt,
            "score_reasons": rng.choice([None, '["+25 phone"]', ["+10 email"], "not json", "{}", 5, '"str"']),
            "utm": rng.choice([None, "", '{"a":"b"}', {"c": 1}, {}, '{"z":1}']), "page_url": rng.choice([None, "https://x.test"])}
    appt = {"id": rng.choice(["id-1", 3]), "starts_at": dt, "ends_at": dt.replace(microsecond=micros), "name": "A", "phone": "", "email": None, "notes": "n", "status": "booked"}
    tz = rng.choice(["", "Pacific/Auckland"])
    try:
        lead_out = events.lead_view(lead)
    except ValueError:  # json.JSONDecodeError: Python itself raises on non-JSON utm text
        lead_out = None
    view_cases.append({"secs": secs, "micros": micros, "tz": tz,
                       "lead": {k: v for k, v in lead.items() if k != "created_at"}, "lead_out": lead_out,
                       "appt": {k: v for k, v in appt.items() if k not in ("starts_at", "ends_at")}, "appt_out": events.appointment_view(appt, tz)})

print(json.dumps({"tools": tool_cases, "capture": capture_cases, "search": search_cases, "twenty": twenty_cases, "urls": url_cases,
                  "delivery": delivery_cases, "views": view_cases}, ensure_ascii=False, indent=0, default=str))
