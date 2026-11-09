"""Batch-13 golden vectors: channel authorization, owner knowledge, phone-setup validation, owner-auth retention limits,
the enquirer acknowledgement flow and the knowledge ingest rules, all from the live Python modules with fake databases.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors13.py > ../concierge-stack/core-rs/parity/vectors13.json

Nothing is sent and no network is used. Embeddings and the LLM are replaced by deterministic fakes.
"""
import asyncio
import json
import os
import random
import sys

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from pydantic import ValidationError  # noqa: E402

from app import acknowledgements, channel_authorization, db, ingest, llm, managed_phone, mobile_connections  # noqa: E402
from app import owner_knowledge, owner_maintenance, tenants  # noqa: E402
from app.crawler import Page  # noqa: E402

rng = random.Random(20261120)
out = {}


def run(coro):
    return asyncio.run(coro)


class Rep(str):
    """A long generated string, stored in the vectors as {"$rep": [unit, count]} instead of its full text."""

    def __new__(cls, unit, count):
        o = super().__new__(cls, unit * count)
        o.spec = {"$rep": [unit, count]}
        return o


def compact(v):
    if isinstance(v, Rep):
        return v.spec
    if isinstance(v, dict):
        return {k: compact(x) for k, x in v.items()}
    if isinstance(v, list):
        return [compact(x) for x in v]
    return v


def verdict(model, data):
    """Outcome of a pydantic model on `data`: the validated values, or the list of (loc, type) error pairs."""
    try:
        m = model.model_validate(data)
        return {"ok": m.model_dump()}
    except ValidationError as e:
        return {"errors": [[".".join(str(p) for p in err["loc"]), err["type"]] for err in e.errors()]}


class CM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


# ---- channel authorization ------------------------------------------------------------------------------------------
chan = {"readiness": [], "request": [], "membership": []}
CH = list(channel_authorization.CHANNELS)
for _ in range(120):
    channels = {k: {"authorized": rng.choice([True, False, 1, 0])} for k in rng.sample(CH, rng.randint(0, 7))}
    checks = {k: rng.choice([True, False, 1, 0, None]) for k in rng.sample(CH + ["other"], rng.randint(0, 6))}
    chan["readiness"].append({"channels": channels, "checks": checks, "out": channel_authorization.readiness(channels, checks)})

raw_chan = [None, "telephone", "call_recording", "email_read", "email_send", "sms_read", "sms_send", "social",
            "Telephone", "email", "", " social", 5, ["social"]]
bools = [True, False, None, "true", "false", "yes", 1, 0, 2, "1", "0", "on", "off", "t", "f", "n", "maybe", 1.0, 0.0, "", "TRUE", "Yes", " true", "true ", "OFF", -1, 1.5, [], {}]
for c in raw_chan:
    for a in bools:
        for k in bools:
            if c not in ("social", "telephone", None, 5) and rng.random() > 0.15:
                continue
            data = {"channel": c, "authorized": a, "acknowledgement": k}
            chan["request"].append({"in": data, "out": verdict(channel_authorization.ChannelAuthorization, data)})
for data in [{"channel": "social", "authorized": True}, {"channel": "social", "acknowledgement": True}, {"authorized": True, "acknowledgement": True},
             {}, {"channel": "social", "authorized": True, "acknowledgement": True, "extra": 1}]:
    chan["request"].append({"in": data, "out": verdict(channel_authorization.ChannelAuthorization, data)})


class AuthPool:
    def __init__(self, v):
        self.v = v

    async def fetchval(self, sql, *a):
        return self.v


for c in CH + ["", "Telephone", "social ", "email", "x"]:
    for v in (True, False, None, 1, 0):
        db.pool = lambda v=v: AuthPool(v)
        chan["membership"].append({"channel": c, "stored": v, "out": run(channel_authorization.is_authorized("t", c))})
out["channel"] = chan

# record_authorization: the ValueError guard, with a recording fake connection
rec = []
for authorized in (True, False):
    for ack in (True, False):
        calls = []

        class Conn:
            def transaction(self):
                return CM()

            async def fetchrow(self, sql, *a):
                calls.append(("row", a))
                return {"authorized": a[2], "updated_at": "T"}

            async def execute(self, sql, *a):
                calls.append(("audit", a))

        class Pool:
            def acquire(self):
                return CM(Conn())

        db.pool = lambda: Pool()
        body = channel_authorization.ChannelAuthorization(channel="social", authorized=authorized, acknowledgement=ack)
        try:
            res = run(channel_authorization.record_authorization("t1", "a1", body))
            o = {"ok": {k: (v if k != "updated_at" else "T") for k, v in res.items()}}
        except ValueError as e:
            o = {"error": str(e)}
        rec.append({"authorized": authorized, "ack": ack, "out": o, "calls": [[k, list(a)] for k, a in calls]})
out["record"] = rec

# ---- owner knowledge -------------------------------------------------------------------------------------------------
know = {"validate": [], "identity": [], "ids": []}
titles = ["Price list", "  padded  ", "x" * 120, "x" * 121, "", " ", "\t", "a\x00b", "a\x1fb", "a\x7fb", "tab\there", "new\nline", "cr\rlf\r\nx",
          "Ünï", "日本語", Rep("😀", 120), Rep("😀", 121), " nbsp ", "a b", "a\x85b", "﻿bom"]
texts = ["Hello", "  hi  ", "", "   ", "\n\n", "a\x00", "line1\r\nline2\rline3", "tab\tok", Rep("x", 100_000), Rep("x", 100_001), Rep("é", 50_000), Rep("é", 50_001),
         Rep("😀", 25_000), Rep("😀", 25_001), "\x0b", "\x0c", "\x1c", "\x7f", "\u0085", "  ok  "]
for t in titles:
    for x in ("Body text", texts[0]):
        d = {"title": t, "text": x}
        know["validate"].append({"in": compact(d), "out": verdict(owner_knowledge.BusinessDocument, d)})
for x in texts:
    d = {"title": "T", "text": x}
    know["validate"].append({"in": compact(d), "out": verdict(owner_knowledge.BusinessDocument, d)})
for d in [{"title": 1, "text": "x"}, {"title": "x", "text": None}, {"title": "x"}, {"text": "x"}, {"title": "x", "text": "y", "extra": 1},
          {"title": ["x"], "text": {"a": 1}}, {"title": True, "text": 1.5}, {"title": b"x".decode(), "text": "y"}]:
    know["validate"].append({"in": compact(d), "out": verdict(owner_knowledge.BusinessDocument, d)})

import hashlib  # noqa: E402

for t in ["Price list", "PRICE LIST", "price list", "Straße", "STRASSE", "ǅ", "İstanbul", "ΣΑΣ", "σας", "ς", "ﬁ", "ŉ", "Ǆ", "ǆ", "ᾈ", "ẞ", "日本", "😀",
          "K", "Å", "ϐ", "ᲀ", "Ꭰ", "ꭰ", "ß" * 3]:
    know["identity"].append({"title": t, "id": hashlib.sha256(t.casefold().encode()).hexdigest()})
captured = {}


async def fake_get_by_id(tid):
    return {"id": tid, "name": "N"}


async def fake_ingest_text(tenant, label, text, title=""):
    captured["args"] = [label, text, title]
    return {"chunks": 3}


tenants.get_by_id = fake_get_by_id
owner_knowledge.ingest.ingest_text = fake_ingest_text
for t, x in [("Price list", "A"), ("STRASSE", "B"), ("Straße", "B")]:
    r = run(owner_knowledge.save("t1", owner_knowledge.BusinessDocument(title=t, text=x)))
    know["identity"].append({"title": t, "save": r, "args": captured["args"]})
good = "a" * 64
for i in [good, "A" * 64, "a" * 63, "a" * 65, "", "g" * 64, good + "\n", "\n" + good, good + " ", "٠" * 64, "a" * 32 + "A" + "a" * 31]:
    class DelPool:
        def acquire(self):
            return CM(DConn())

    class DConn:
        def transaction(self):
            return CM()

        async def execute(self, sql, *a):
            pass

        async def fetchval(self, sql, *a):
            return 1

    db.pool = lambda: DelPool()
    know["ids"].append({"id": i, "out": run(owner_knowledge.remove("t1", i))})
out["knowledge"] = know

# ---- phone setup and mobile connection validation ---------------------------------------------------------------------
phone = {"setup": [], "mobile": [], "steps": []}
nums = ["+64211234567", "+6421123", "+642112", "+1234567", "+123456789012345", "+1234567890123456", "+0211234567", "64211234567", "+64 21 123 4567",
        "+6421123456\n", "\n+6421123456", "+٦٤٢١١٢٣٤٥٦٧", "", None, 64211234567, "+64211234567 ", " +64211234567", "+6421123456a"]
conns = [None, "existing_sip", "existing_twilio", "mobile_forwarding", "other", "", "Existing_SIP", 3]
modes = [None, "all_calls", "unanswered", "none", "", 1]
for a in nums:
    for b in nums[:6] + [None]:
        d = {"designated_number": a, "owner_number": b}
        phone["setup"].append({"in": d, "out": verdict(managed_phone.PhoneSetup, d)})
for c in conns:
    for m in modes:
        d = {"designated_number": "+64211234567", "owner_number": "+64277654321"}
        if c is not None:
            d["connection"] = c
        if m is not None:
            d["answer_mode"] = m
        phone["setup"].append({"in": d, "out": verdict(managed_phone.PhoneSetup, d)})
for d in [{}, {"designated_number": "+64211234567"}, {"owner_number": "+64277654321"},
          {"designated_number": "+64211234567", "owner_number": "+64277654321", "x": 1},
          {"designated_number": "+64211234567", "owner_number": "+64277654321", "x": 1, "y": 2}]:
    phone["setup"].append({"in": d, "out": verdict(managed_phone.PhoneSetup, d)})
for a in nums:
    for c in [None, "spark_nz", "other", "Spark_NZ", "", 1]:
        d = {"destination": a}
        if c is not None:
            d["carrier"] = c
        phone["mobile"].append({"in": d, "out": verdict(mobile_connections.MobileConnection, d)})
for d in [{}, {"carrier": "other"}, {"destination": "+64211234567", "extra": 1}]:
    phone["mobile"].append({"in": d, "out": verdict(mobile_connections.MobileConnection, d)})
out["phone"] = phone

# ---- owner auth retention ---------------------------------------------------------------------------------------------
maint = []
for size in (-1, 0, 1, 2, 500, 4999, 5000, 5001, 10**6):
    for dry in (True, False):
        class MConn:
            def transaction(self):
                return CM()

            async def fetchval(self, sql, *a):
                return 7

            async def fetch(self, sql, *a):
                return [1, 2]

        try:
            res = run(owner_maintenance.prune_expired(MConn(), batch_size=size, dry_run=dry))
            o = {"ok": res}
        except ValueError as e:
            o = {"error": str(e)}
        maint.append({"size": size, "dry": dry, "out": o})
out["maintenance"] = maint

# ---- acknowledgements ------------------------------------------------------------------------------------------------
ack = []
TENANT = {"id": "t-1", "name": "Trendi"}


def ack_case(args, ctx, row, authorized, lead):
    effects = []

    class AConn:
        def transaction(self):
            return CM()

        async def fetchrow(self, sql, *a):
            if "pending_ack FROM conversations" in sql:
                effects.append(["select_pending", list(a)])
                return None if row is None else {"pending_ack": row["pending"]}
            if "FROM leads" in sql:
                effects.append(["select_lead", list(a)])
                return None if lead is None else {"id": lead}
            raise AssertionError(sql)

        async def execute(self, sql, *a):
            tag = "outbox" if "INSERT INTO outbox" in sql else "pending"
            effects.append([tag, [x for x in a]])

    class APool:
        def acquire(self):
            return CM(AConn())

        async def execute(self, sql, *a):
            effects.append(["decline", list(a)])

    async def is_auth(tid, ch):
        effects.append(["authorized", [tid, ch]])
        return authorized

    db.pool = lambda: APool()
    channel_authorization.is_authorized = is_auth
    acknowledgements.channel_authorization.is_authorized = is_auth
    res = run(acknowledgements.request(TENANT, args, ctx))
    return res, effects


recipients = ["", "  ", "a@b.co", "  A@B.CO ", "bad", "a@b", "021 123 4567", "+64 21 123 4567", "+64211234567", "12345", "1", "x" * 3, None,
              0, 5551234567, False, True, " a@b.co ", "a@b.co\n"]
cases = 0
for ctx in ({"dry_run": True}, {}, {"conversation_id": ""}, {"conversation_id": "c-9"}, {"conversation_id": "c-9", "dry_run": False}):
    for requested in (True, False, None, "yes", 1, 0):
        for channel in (None, "email", "sms", "EMAIL", "voice", ""):
            for recipient in recipients:
                for confirmed in (True, False, None, "yes", 1):
                    if rng.random() > 0.12 and not (ctx.get("conversation_id") == "c-9" and requested is True and channel in ("email", "sms")):
                        continue
                    args = {"requested": requested, "channel": channel, "recipient": recipient, "confirmed": confirmed}
                    for k in list(args):
                        if args[k] is None and rng.random() < 0.5:
                            del args[k]
                    key = {"channel": channel, "recipient": (recipient.strip().lower() if channel == "email" else None)
                           } if isinstance(recipient, str) else None
                    rows = [None, {"pending": None}, {"pending": {"declined": True}}, {"pending": {"recipient": "x", "channel": "email"}}]
                    if channel in ("email", "sms") and isinstance(recipient, str):
                        r = recipient.strip().lower() if channel == "email" else None
                        rows.append({"pending": {"channel": channel, "recipient": r or "+64211234567"}})
                        rows.append({"pending": json.dumps({"recipient": r or "+64211234567", "channel": channel})})
                    row = rng.choice(rows)
                    authorized = rng.choice([True, False])
                    lead = rng.choice([None, "l-1"])
                    try:
                        res, eff = ack_case(args, ctx, row, authorized, lead)
                    except Exception as e:  # noqa: BLE001 - a Python crash must be mirrored or declared unsupported
                        ack.append({"args": args, "ctx": ctx, "row": row, "authorized": authorized, "lead": lead, "crash": type(e).__name__})
                        continue
                    ack.append({"args": args, "ctx": ctx, "row": row, "authorized": authorized, "lead": lead, "out": res, "effects": eff})
                    cases += 1
# every deliberate confirmed path, so queueing is certain to be covered
for channel, recipient, norm in [("email", "A@B.co ", "a@b.co"), ("sms", "021 123 4567", "+10211234567"), ("sms", "+64 21 123 4567", "+64211234567"),
                                 ("sms", "12345678", "+12345678")]:
    for lead in (None, "l-1"):
        for authorized in (True, False):
            args = {"requested": True, "channel": channel, "recipient": recipient, "confirmed": True}
            row = {"pending": {"channel": channel, "recipient": norm}}
            res, eff = ack_case(args, {"conversation_id": "c-9"}, row, authorized, lead)
            ack.append({"args": args, "ctx": {"conversation_id": "c-9"}, "row": row, "authorized": authorized, "lead": lead, "out": res, "effects": eff})
out["ack"] = ack

# ---- ingest ---------------------------------------------------------------------------------------------------------
ing = {"store": [], "questions": [], "pgvector": []}
long_text = "\n\n".join(("Paragraph %d. " % i) + "word " * rng.randint(20, 120) for i in range(12))
page_pool = [
    Page("https://a.example/", "Home", "Short page text."),
    Page("https://a.example/about", "", "No title here.\n\nSecond paragraph."),
    Page("https://a.example/long", "Long", long_text),
    Page("manual:faq", "FAQ", "Q1\n\nA1\n\nQ2\n\nA2 " + "x" * 2500),
    Page("https://a.example/empty", "Empty", ""),
    Page("https://a.example/ws", "WS", "   \n\n   "),
    Page("https://a.example/uni", "日本語", "日本語のテキスト。" * 300),
]
for _ in range(28):
    pages = rng.sample(page_pool, rng.randint(0, 5))
    replace_crawled = rng.choice([True, False])
    replace_url = rng.choice([None, "manual:faq", "manual:other"])
    n_records = sum(len(ingest.chunk_text(p.text)) for p in pages)
    vec_len = n_records + rng.choice([0, 0, 0, 0, 1, -1]) if n_records else 0
    vecs = [[round(rng.uniform(-2, 2), rng.randint(0, 9)) for _ in range(rng.randint(0, 4))] for _ in range(max(vec_len, 0))]
    ops = []

    class SConn:
        def transaction(self):
            return CM()

        async def execute(self, sql, *a):
            ops.append(["execute", sql, list(a)])

        async def executemany(self, sql, rows):
            ops.append(["executemany", sql, [list(r) for r in rows]])

    class SPool:
        def acquire(self):
            return CM(SConn())

    async def fake_embed(texts, batch_size=16):
        ops.append(["embed", len(texts), list(texts)])
        return vecs

    db.pool = lambda: SPool()
    ingest.embed_documents = fake_embed
    try:
        n = run(ingest._store("t-1", pages, replace_crawled, replace_url))
        o = {"n": n}
    except RuntimeError as e:
        o = {"error": str(e)}
    ing["store"].append({"pages": [[p.url, p.title, p.text] for p in pages], "replace_crawled": replace_crawled, "replace_url": replace_url,
                         "vectors": vecs, "out": o, "ops": ops})

for content in ["", "1. First?\n2. Second?\n\n- Third?\n• Fourth?", "  - 12.  \nplain\n\n\n", "123\n...\n- \n", "What?\r\nWhy?\rHow?\x0bWhen?\x0cWhere?\x1cWho?\x85Which? Whose? Eh",
                "a\n" * 20, None, "\t\t5. tab question \t", "9 lives?\n10. ten", "—dash\n– en", "-• x •-"]:
    for count in (0, 1, 3, 5, 7):
        rows = [{"title": "T%d" % i, "content": "C" * rng.randint(0, 900)} for i in range(rng.choice([0, 1, 3, 14]))]
        calls = []

        class QPool:
            async def fetch(self, sql, *a):
                calls.append(["fetch", list(a)])
                return rows

            async def execute(self, sql, *a):
                calls.append(["execute", list(a)])

        class Msg:
            def __init__(self, c):
                self.content = c

        async def fake_complete(messages, tools=None, temperature=0.3, max_tokens=600):
            calls.append(["llm", messages, temperature, max_tokens])
            return Msg(content)

        db.pool = lambda: QPool()
        ingest.llm.complete = fake_complete
        res = run(ingest.generate_demo_questions({"id": "t-1", "name": "Biz"}, count))
        ing["questions"].append({"content": content, "count": count, "rows": rows, "out": res, "calls": calls})

from app.embeddings import to_pgvector  # noqa: E402

for vec in [[], [0.0], [-0.0], [1.0], [0.5, -0.25], [1e-7], [-1e-7], [123456.7890125], [0.0000005], [0.0000015], [2.5e-6], [1e21], [1.7976931348623157e308],
            [5e-324], [0.1 + 0.2], [1 / 3, 2 / 3], [-1 / 3], [0.9999995], [0.9999994999], [1e15 + 0.3]]:
    ing["pgvector"].append({"vec": vec, "out": to_pgvector(vec)})
for _ in range(300):
    vec = [rng.uniform(-1, 1) * 10 ** rng.randint(-8, 8) for _ in range(rng.randint(1, 5))]
    ing["pgvector"].append({"vec": vec, "out": to_pgvector(vec)})
ing["pgvector_special"] = [{"vec": ["nan", "inf", "-inf"], "out": to_pgvector([float("nan"), float("inf"), float("-inf")])}]
out["ingest"] = ing

json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"))
