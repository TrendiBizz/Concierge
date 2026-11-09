"""Batch-10 golden vectors: the real cloudflare_inbound.handle() with a fake database and clock, plus draft/enquiry helpers.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors10.py > ../concierge-stack/core-rs/parity/vectors10.json
"""
import asyncio
import json
import os
import random
import sys
from types import SimpleNamespace

from fastapi import HTTPException

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import automation, channel_authorization, convo, db, email_drafts, owner_notifications, tenants  # noqa: E402
from app import cloudflare_inbound as cf  # noqa: E402

rng = random.Random(20261118)
NOW = 1_800_000_000
TENANT = "0a3e7155-2f19-4527-bee1-f2dec7b676c7"
SECRET = "s" * 40
fx = {"authorized": True, "unknown": False}
effects = {}


class AsyncCM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


class Conn:
    def transaction(self):
        return AsyncCM()

    async def execute(self, sql, *a):
        if "enquiry_sources" in sql:
            effects["source"] = a

    async def fetchrow(self, sql, *a):
        if sql.startswith("SELECT * FROM leads"):
            return None
        if sql.startswith("INSERT INTO leads"):
            effects["lead"] = a
            return {"id": "lead-1", "tenant_id": TENANT}
        raise AssertionError(sql)


class Pool:
    def acquire(self):
        return AsyncCM(Conn())

    async def fetchrow(self, sql, *a):
        if "inbound_mailboxes" in sql:
            return None if fx["unknown"] else {"tenant_id": TENANT}
        if "INSERT INTO email_drafts" in sql:
            effects["draft"] = a
            return {"id": 1, "sender": a[2]}
        raise AssertionError(sql)


async def is_authorized(tenant_id, channel):
    return fx["authorized"]


async def get_by_id(tid):
    return {"id": TENANT, "name": "Trendi", "email_auto_reply": False}


async def get_or_create(tenant, session, channel, page, utm):
    effects["session"] = session
    return "conv-1"


async def queue(tenant, subject, body, dedupe, *, lead_id=None, connection=None):
    effects["owner"] = (subject, body, dedupe)


async def noop(*a, **k):
    return None


db.pool = lambda: Pool()
channel_authorization.is_authorized = is_authorized
tenants.get_by_id = get_by_id
convo.get_or_create = get_or_create
owner_notifications.queue = queue
automation.on_lead_created = noop
cf.time = SimpleNamespace(time=lambda: NOW)


class Req:
    def __init__(self, headers, body):
        self.headers, self._b = headers, body

    async def body(self):
        return self._b


BASE = {"message_id": "<abc123@mail.example>", "recipient": "Help@Trendi.Test", "sender": "ann@example.com", "subject": "Hello  there", "text": "Can I book tomorrow?"}


def run(enabled, secret, ts, sig, body, authorized=True, unknown=False):
    effects.clear()
    fx.update(authorized=authorized, unknown=unknown)
    cf.get_settings = lambda: SimpleNamespace(inbound_cloudflare_enabled=enabled, inbound_cloudflare_secret=secret)
    headers = {"x-concierge-timestamp": ts, "x-concierge-signature": sig}
    try:
        res = asyncio.run(cf.handle(Req(headers, body)))
        return {"ok": {"result": res, "draft": list(effects["draft"]), "session": effects["session"], "lead": list(effects["lead"]), "source": list(effects["source"]), "owner": list(effects["owner"])}}
    except HTTPException as e:
        return {"status": e.status_code, "detail": e.detail}
    except Exception as e:  # noqa: BLE001
        return {"exception": type(e).__name__}


def mk(payload=None, **over):
    p = {**BASE, **(payload or {})}
    for k in over.pop("drop", []):
        p.pop(k, None)
    return json.dumps(p, ensure_ascii=False).encode()


cases = []


def add(name, *, enabled=True, secret=SECRET, ts=None, sig=None, body=None, authorized=True, unknown=False, sign_with=None, ts_sign=None):
    body = body if body is not None else mk()
    ts = str(NOW) if ts is None else ts
    sig = cf.signature(sign_with or secret, ts_sign or ts, body) if sig is None and ts.isascii() else (sig or "0" * 64)
    out = run(enabled, secret, ts, sig, body, authorized, unknown)
    cases.append({"name": name, "enabled": enabled, "secret": secret, "ts": ts, "sig": sig, "body_hex": body.hex(), "now": NOW, "out": out})


add("valid")
add("disabled", enabled=False)
add("short secret", secret="s" * 31)
add("secret of 32 non-ASCII characters", secret="é" * 32)
for label, ts in [("ts now-300", str(NOW - 300)), ("ts now+300", str(NOW + 300)), ("ts now-301", str(NOW - 301)), ("ts now+301", str(NOW + 301)), ("ts empty", ""), ("ts letters", "abc"),
                  ("ts 13 digits", "1" * 13), ("ts 12 digits", "1" * 12), ("ts spaced", " 123"), ("ts signed", "+123"), ("ts zero", "0"), ("ts fullwidth", "１２３")]:
    add(label, ts=ts)
for label, sig in [("sig upper", None), ("sig wrong", "a" * 64), ("sig short", "a" * 63), ("sig long", "a" * 65), ("sig empty", ""), ("sig non-hex", "g" * 64)]:
    good = cf.signature(SECRET, str(NOW), mk())
    add(label, sig={"sig upper": good.upper(), "sig wrong": "a" * 64, "sig short": good[:-1], "sig long": good + "a", "sig empty": "", "sig non-hex": "g" * 64}[label])
add("signed with another secret", sign_with="t" * 40)
add("signed over a different timestamp", ts_sign=str(NOW - 1))
big = json.dumps({**BASE, "text": "x" * 29900}).encode()
add("body exactly at the limit", body=json.dumps({**BASE, "text": "x" * (30000 - len(json.dumps({**BASE, "text": ""})))}).encode())
add("body over the limit", body=json.dumps({**BASE, "text": "x" * (30001 - len(json.dumps({**BASE, "text": ""})))}).encode())
add("over the limit with a bad signature", body=b"x" * 30001, sig="a" * 64)
for label, body in [("not json", b"nope"), ("json array", b"[1,2]"), ("json string", b'"x"'), ("invalid utf-8", b'{"a":"\xff"}'), ("empty body", b""),
                    ("extra field", mk({"extra": "x"})), ("missing field", mk(drop=["subject"])), ("number message id", mk({"message_id": 5})), ("null text", mk({"text": None})),
                    ("sender 320", mk({"sender": "a" * 308 + "@example.com"})), ("sender 321", mk({"sender": "a" * 309 + "@example.com"})),
                    ("subject 250", mk({"subject": "s" * 250})), ("subject 251", mk({"subject": "s" * 251})),
                    ("recipient no tld", mk({"recipient": "help@trendi"})), ("recipient angle", mk({"recipient": "<help@trendi.test>"})), ("recipient spaces", mk({"recipient": " Help@Trendi.Test "})),
                    ("recipient int", mk({"recipient": 5})), ("duplicate keys", b'{"message_id":"x","message_id":"<abc@m.test>","recipient":"h@t.test","sender":"a@b.co","subject":"s","text":"t"}'),
                    ("text empty", mk({"text": ""})), ("text blank", mk({"text": "  \n "})), ("text 20000", mk({"text": "t" * 20000})), ("text 20001", mk({"text": "t" * 20001})),
                    ("text with NUL", mk({"text": "a\u0000b"})), ("message id 500", mk({"message_id": "m" * 500})), ("message id 501", mk({"message_id": "m" * 501})),
                    ("message id bad chars", mk({"message_id": "a b"})), ("message id odd chars", mk({"message_id": "<a+b=c@d.e>/x"})),
                    ("sender not an email", mk({"sender": "not-an-email"})), ("sender with newline", mk({"sender": "ann@example.com\nBcc: x@y.zz"})), ("sender padded", mk({"sender": "  ann@example.com  "})),
                    ("unicode subject", mk({"subject": "Café\tmenu\n\nprices"})), ("unicode text", mk({"text": "日本語 😀"}))]:
    add(label, body=body)
add("unknown mailbox", unknown=True)
add("business has not authorized inbound email", authorized=False)

# ---- helpers run live -----------------------------------------------------------------------------------------------
address_cases = []
for v in ["a@b.co", " a@b.co ", "a@b", "a b@c.de", "a@b.co\n", "a@b.co\r\nBcc: x@y.zz", "", "日本@x.jp", "a@@b.co", "A@B.CO"]:
    try:
        out = email_drafts._address(v)
    except email_drafts.DraftError:
        out = None
    address_cases.append({"in": v, "out": out})
subject_cases = [{"in": v, "out": email_drafts._subject(v)} for v in ["", "  a   b  ", "x" * 300, "a\tb\nc", "é " * 200, "　lead　"]]

print(json.dumps({"cases": cases, "address": address_cases, "subject": subject_cases, "secret": SECRET, "tenant": TENANT}, ensure_ascii=False, indent=0, default=str))
