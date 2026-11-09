"""Batch-15 golden vectors: settings rules, the owner business profile, email drafts and tenant record handling, from the live
Python modules with fake databases and a fake language model (nothing is sent, no network).

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors15.py > ../concierge-stack/core-rs/parity/vectors15.json
"""
import asyncio
import json
import os
import random
import sys
from zoneinfo import available_timezones

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from pydantic import ValidationError  # noqa: E402

from app import config, db, email_drafts, llm, owner_onboarding, tenants  # noqa: E402

rng = random.Random(20261122)
out = {}


def run(coro):
    return asyncio.run(coro)


class CM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


def verdict(model, data):
    try:
        m = model.model_validate(data)
        return {"ok": m.model_dump(exclude_unset=True, exclude_none=True)}
    except ValidationError as e:
        return {"errors": [[".".join(str(p) for p in err["loc"]), err["type"]] for err in e.errors()]}


# ---- settings -------------------------------------------------------------------------------------------------------------
S = {"portal": [], "props": []}
portals = ["https://concierge.trendibizz.com/owner-ui", "http://localhost/owner-ui", "http://127.0.0.1:8000/owner-ui", "http://[::1]/owner-ui", "http://example.com/owner-ui",
           "https://example.com/owner-ui/", "https://example.com/owner-ui?x=1", "https://example.com/owner-ui#f", "https://u:p@example.com/owner-ui",
           "https://u@example.com/owner-ui", "https://@example.com/owner-ui", "https:///owner-ui", "https://example.com", "https://example.com/other",
           "HTTPS://EXAMPLE.COM/owner-ui", "https://example.com:8443/owner-ui", "https://exa mple.com/owner-ui", "ftp://example.com/owner-ui", "", "owner-ui",
           "https://[::1/owner-ui", "http://LOCALHOST/owner-ui", "http://localhost.:80/owner-ui", "https://example.com/owner-ui;p", "https://example.com/Owner-UI",
           "https://ünï.example/owner-ui", "http://[v1.x]/owner-ui", "http://127.0.0.2/owner-ui", "https://example.com//owner-ui", 5, None, ["x"]]
for v in portals:
    try:
        config.Settings(owner_portal_url=v)
        o = {"ok": True}
    except ValidationError as e:
        o = {"errors": [x["type"] for x in e.errors()]}
    S["portal"].append({"url": v, "out": o})
for _ in range(400):
    kw = {
        "xai_api_key": rng.choice(["", "k"]), "llm_api_key": rng.choice(["", "l"]),
        "voice_model": rng.choice(["", "grok-voice-3.0", "m&x"]), "xai_realtime_url": rng.choice(["wss://a/v1/realtime", "wss://a/v1/realtime?x=1", "wss://a"]),
        "sms_provider": rng.choice(["twilio", "smsgate", "none", " Twilio ", "SMSGATE", "", "other"]),
        "twilio_account_sid": rng.choice(["", "AC"]), "twilio_auth_token": rng.choice(["", "t"]), "twilio_from_number": rng.choice(["", "+1"]),
        "twilio_messaging_service_sid": rng.choice(["", "MG"]), "smsgate_base_url": rng.choice(["", "https://s"]), "smsgate_username": rng.choice(["", "u"]),
        "smsgate_password": rng.choice(["", "p"]), "smtp_host": rng.choice(["", "h"]), "smtp_from": rng.choice(["", "f@x"]),
    }
    s = config.Settings(**kw)
    S["props"].append({"kw": kw, "effective_llm_key": s.effective_llm_key, "voice_ws_url": s.voice_ws_url, "sms_configured": s.sms_configured,
                       "email_configured": s.email_configured})
out["settings"] = S

# ---- owner business profile -------------------------------------------------------------------------------------------------
P = {"validate": [], "status": []}
good_hours = {"mon": [["09:00", "17:00"]], "tue": [["09:00", "12:00"], ["13:00", "17:00"]], "sun": []}
vals = {
    "email_auto_reply": [True, False, None, "yes", "no", 1, 0, 2, "maybe", [], 0.0, 1.5, "TRUE"],
    "voice_enabled": [True, False, "on", 5],
    "native_booking": [True, False, "off", {}],
    "slot_minutes": [30, 5, 240, 4, 241, "30", "3_0", " 30 ", "_30", "30_", "3__0", "+30", "-5", "٣٠", 30.0, 30.5, True, False, None, "x", [1], {}, 10**30, "1e1", ""],
    "business_hours": [good_hours, {}, {"funday": []}, {"mon": [["09:00", "17:00"]] * 5}, {"mon": [["01:00", "02:00"], ["03:00", "04:00"], ["05:00", "06:00"], ["07:00", "08:00"], ["09:00", "10:00"]]},
                       {"mon": [["01:00", "02:00"], ["03:00", "04:00"], ["05:00", "06:00"], ["07:00", "08:00"]]}, {"mon": [["17:00", "09:00"]]}, {"mon": [["09:00", "10:00"], ["09:30", "11:00"]]},
                       {"mon": [["10:00", "11:00"], ["09:00", "10:30"]]}, {"mon": [["09:00"]]}, {"mon": [["9:00", "17:00"]]}, {"mon": [["24:00", "25:00"]]},
                       {"mon": "x"}, {"mon": [5]}, {"mon": [["09:00", 5]]}, [1], 5, None, {"mon": [["09:00", "09:00"]]}, {"mon": [["٠٩:00", "17:00"]]},
                       {d: [] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "mon2"]}, {"MON": []}, {"mon": [["09:00", "10:00"], ["10:00", "11:00"]]},
                       {"mon": [["00:00", "23:59"]]}, {"mon": [["09:00", "17:00"], ["09:00", "17:00"]]}, {"mon": [["09:00", "17:00\n"]]}],
    "name": ["Acme", "  Acme  ", "", "   ", "a\x00b", "a\tb", "x" * 160, "x" * 161, 5, None, "日本語", "  "],
    "site_url": ["https://example.com", " https://example.com/x ", "", "  ", "http://example.com", "https://localhost", "https://example.com:99999", "https://example.com:80",
                 "https://u:p@example.com", "https://example.com#f", "https://exa mple.com", "https://example.com/a b", "https://example.com/\x01", "https://[::1]/",
                 "https://[::1", "https://a.b/" + "x" * 2040, "https://a.b/" + "x" * 2050, "ftp://x.y", "https://-.-", "https://ünï.example", "https://example.com:",
                 "https://example.com:abc", "https://example..com", "https://.", 5, None],
    "greeting": ["Hello", "  hi  ", "a\x00", "tab\tok\nnl", "x" * 500, "x" * 501, "\x7f", "", 5],
    "notify_phone": ["+64211234567", "", "  +64211234567 ", "+6421123", "+0211234567", "021123456", "+64211234567890123", "+" + "1" * 15, "+" + "1" * 14, "x" * 16, "x" * 17,
                     "+٦٤٢١١٢٣٤٥٦٧", None, 5],
    "notify_email": ["A@B.co", " a@b.co ", "", "  ", "a@b", "a@@b.co", "a@.co", "a@b.", "@b.co", "a b@c.co", "a@b .co", "x" * 250 + "@b.co", "a@b.c@d.e", "ÄÖ@B.CO", None, 7],
    "timezone": ["Pacific/Auckland", "UTC", "utc", "Europe/London", "", "Nope/Zone", "../etc/passwd", "/etc/passwd", "Pacific/../Auckland", "Pacific\\Auckland", "EST5EDT",
                 "zone.tab", "America/Argentina/Buenos_Aires", "x" * 100, "x" * 101, None, 5, "Etc/GMT+5", "GMT", "Europe/Kyiv", "Asia/Kolkata", " UTC", "UTC ", "America", "Pacific"],
}
for field, options in vals.items():
    for v in options:
        d = {field: v}
        P["validate"].append({"in": d, "out": verdict(owner_onboarding.OwnerBusinessProfile, d)})
# every real zone Python knows must be accepted
P["zones"] = sorted(available_timezones() - {"localtime", "posixrules"})  # host-specific files, not zones
for _ in range(500):
    d = {}
    for f in rng.sample(list(vals), rng.randint(1, 5)):
        d[f] = rng.choice(vals[f])
    P["validate"].append({"in": d, "out": verdict(owner_onboarding.OwnerBusinessProfile, d)})
for d in [{}, {"extra": 1}, {"name": "A", "extra": 1}, {"name": "A", "other": 2, "more": 3}, [], "x", None]:
    try:
        P["validate"].append({"in": d, "out": verdict(owner_onboarding.OwnerBusinessProfile, d)})
    except Exception as e:  # noqa: BLE001
        P["validate"].append({"in": d, "out": {"crash": type(e).__name__}})


class St:
    def __init__(self, **k):
        self.__dict__.update(k)

    @property
    def effective_llm_key(self):
        return self.llm_api_key or self.xai_api_key


for _ in range(300):
    tenant = {"slug": rng.choice(["a", "b", "c", None]), "site_url": rng.choice([None, "", "https://x.y"]), "voice_enabled": rng.choice([True, False, None])}
    st = St(website_verified_tenants=rng.choice(["", "a", "a,b", " b , c ", ",,", "c,"]), llm_api_key=rng.choice(["", "k"]), xai_api_key=rng.choice(["", "x"]))
    P["status"].append({"tenant": tenant, "verified": st.website_verified_tenants, "llm": st.llm_api_key, "xai": st.xai_api_key,
                        "out": owner_onboarding.website_channel_status(tenant, st)})
out["profile"] = P

# ---- email drafts -----------------------------------------------------------------------------------------------------------------
E = {"address": [], "subject": [], "propose": [], "create": [], "approve": []}
for a in ["a@b.co", " a@b.co ", "a@b", "", "a@b.co\n", "a\r@b.co", "A@B.CO", "a b@c.co", "x@y.z\r\nBcc: z@z.zz", "\ta@b.co\t", "a@b.co\x0b", "ä@b.co"]:
    try:
        E["address"].append({"in": a, "out": {"ok": email_drafts._address(a)}})
    except email_drafts.DraftError as e:
        E["address"].append({"in": a, "out": {"err": str(e)}})
for sbj in ["", "Hello", "  a   b \n c\t d  ", "x" * 300, "é" * 260, "a b", "a b", "\x1c\x1d x", "line1\r\nline2", "😀" * 251]:
    E["subject"].append({"in": sbj, "out": email_drafts._subject(sbj)})


async def fake_retrieve(tenant_id, query):
    fake_retrieve.q = query
    return [{"content": c} for c in fake_retrieve.contents]


import app.rag as rag  # noqa: E402

rag.retrieve = fake_retrieve
for _ in range(60):
    contents = [("K%d " % i) + "w" * rng.choice([5, 400, 6000]) for i in range(rng.choice([0, 1, 3]))]
    fake_retrieve.contents = contents
    tenant = {"id": "t", "name": rng.choice(["Acme", "Ünï & Co"]), "persona": rng.choice([None, "", "Be kind", "p" * 1500])}
    reply = rng.choice(["", "  ", " Hello \n", "r" * 11000, None])
    sender, subject, body = rng.choice(["a@b.co", " a@b.co "]), rng.choice(["Hi", " a  b ", "s" * 300]), rng.choice(["Body", "b" * 2500, "b" * 13000])
    seen = {}

    class Msg:
        content = reply

    async def fake_complete(messages, tools=None, temperature=0.3, max_tokens=600):
        seen["call"] = [messages, tools, temperature, max_tokens]
        return Msg()

    llm.complete = fake_complete
    try:
        res = {"ok": run(email_drafts.propose(tenant, sender, subject, body))}
    except email_drafts.DraftError as e:
        res = {"err": str(e)}
    E["propose"].append({"tenant": tenant, "contents": contents, "sender": sender, "subject": subject, "body": body, "reply": reply, "out": res,
                         "query": fake_retrieve.q, "call": seen.get("call")})

for _ in range(120):
    sender = rng.choice(["a@b.co", "bad", " a@b.co "])
    inbound = rng.choice(["x", "", "  ", "i" * 21000])
    reply = rng.choice(["r", "", " ", "r" * 11000])
    source = rng.choice(["", "  ", " src-1 ", "s" * 600])
    subject = rng.choice(["", "Hi  there", "s" * 300])
    captured = {}

    class CPool:
        async def fetchrow(self, sql, *a):
            captured["args"] = list(a)
            return {"x": 1}

    db.pool = lambda: CPool()
    try:
        r = run(email_drafts.create("t1", sender, subject, inbound, reply, source))
        o = {"ok": True, "args": captured["args"]}
    except email_drafts.DraftError as e:
        o = {"err": str(e)}
    E["create"].append({"in": [sender, subject, inbound, reply, source], "out": o})

for outbox_enabled in (True, False):
    for email_cfg in (True, False):
        for row in [None, {"status": "approved", "reply_body": "x", "sender": "a@b.co", "subject": "S"}, {"status": "draft", "reply_body": "REVIEW REQUIRED — x", "sender": "a@b.co", "subject": "S"},
                    {"status": "draft", "reply_body": "OK", "sender": "a@b.co", "subject": "S"}, {"status": "draft", "reply_body": "OK", "sender": "a@b.co", "subject": ""},
                    {"status": "draft", "reply_body": "OK", "sender": "a@b.co", "subject": "s" * 300}]:
            effects = []

            class AConn:
                def transaction(self):
                    return CM()

                async def fetchrow(self, sql, *a):
                    effects.append(["fetchrow", sql.split()[0], list(a)])
                    return row if sql.startswith("SELECT") else {"status": "approved"}

                async def execute(self, sql, *a):
                    effects.append(["execute", sql.split()[0], list(a)])

            class APool:
                def acquire(self):
                    return CM(AConn())

            db.pool = lambda: APool()
            config.get_settings = lambda o=outbox_enabled, e=email_cfg: St(outbox_enabled=o, email_configured=e)
            email_drafts.get_settings = config.get_settings
            try:
                r = run(email_drafts.approve("t1", 9))
                o = {"ok": r}
            except email_drafts.DraftError as e:
                o = {"err": str(e)}
            E["approve"].append({"outbox": outbox_enabled, "email": email_cfg, "row": row, "out": o, "effects": effects})
out["drafts"] = E

# ---- tenants ----------------------------------------------------------------------------------------------------------------------
T = {"update": [], "create": [], "clone": [], "view": [], "load": []}
field_values = {
    "name": "N", "site_url": "https://a.b", "allowed_origins": ["https://a.b"], "persona": "p", "greeting": "g", "cta_text": "c", "accent_color": "#fff", "voice": "eve",
    "voice_enabled": True, "voice_daily_limit": 5, "phone_enabled": False, "phone_daily_limit": 3, "booking_url": "https://b", "lead_webhook_url": "https://w", "incentive": "i",
    "timezone": "UTC", "business_hours": {"mon": [["09:00", "17:00"]], "ü": []}, "slot_minutes": 30, "min_notice_hours": 2, "max_days_ahead": 30, "native_booking": True,
    "notify_email": "a@b.co", "notify_phone": "+1", "email_auto_reply": False, "sms_enabled": True, "sms_from": "+2", "lead_sms_template": "t", "review_url": "https://r",
    "lead_value_cents": 100, "sla_minutes": 15, "sla_min_score": 50, "campaigns_enabled": False, "scoring": {"a": 1, "b": "é"}, "weekly_digest": True,
    "id": "no", "slug": "no", "public_key": "no", "report_token": "no", "bogus": 1,
}
for _ in range(220):
    keys = rng.sample(list(field_values), rng.randint(0, 8))
    fields = {k: field_values[k] for k in keys}
    for k in list(fields):
        if rng.random() < 0.15:
            fields[k] = None
    cap = {}

    class UPool:
        async def fetchrow(self, sql, *a):
            cap["call"] = [sql, list(a)]
            return rng_row

    rng_row = rng.choice([None, {"slug": "s", "business_hours": '{"mon": []}', "demo_questions": "[1]"}, {"slug": "s", "business_hours": {"mon": []}, "demo_questions": None}])
    db.pool = lambda: UPool()
    res = run(tenants.update("slug-1", fields))
    T["update"].append({"fields": fields, "row": rng_row, "call": cap.get("call"), "out": res})

for conflicts in (0, 1, 2, 5):
    for name, slug in [("Acme Ltd", None), ("Ünï Café!", None), ("Acme", "My Slug"), ("   ", None), ("x" * 200, None), ("a--b", "a--b")]:
        calls = []
        count = {"n": 0}

        class CPool2:
            async def fetchrow(self, sql, *a):
                calls.append([sql.split()[0], list(a)])
                if sql.lstrip().startswith("INSERT"):
                    count["n"] += 1
                    return None if count["n"] <= conflicts else {"id": "i-1", "slug": a[0]}
                return {"id": "i-1", "calendar_token": a[1]}

        tenants.new_public_key = lambda: "pk_fixed"
        tenants.new_report_token = lambda: "rt_fixed"
        db.pool = lambda: CPool2()
        run(tenants.create(name, rng.choice([None, "https://a.b"]), slug, allowed_origins=["https://o"], persona="p"))
        T["create"].append({"name": name, "slug": slug, "conflicts": conflicts, "calls": calls})

for _ in range(40):
    source = {k: v for k, v in field_values.items() if rng.random() < 0.5}
    for k in list(source):
        if rng.random() < 0.1:
            source[k] = None
    ops = []

    async def fake_create(name, site_url, slug=None, **kw):
        ops.append(["create", name, site_url, slug])
        return {"slug": "new-slug"}

    async def fake_update(slug, fields):
        r = rng.choice([{"slug": slug, "updated": True}, None])
        ops.append(["update", slug, fields, r])
        return r

    tenants.create, tenants.update = fake_create, fake_update
    res = run(tenants.clone(source, "Copy", "https://c.d", slug=None))
    T["clone"].append({"source": source, "ops": ops, "out": res})
tenants.create = tenants.update = None

for tenant in [{"name": "A", "greeting": "", "cta_text": "c", "accent_color": "#1", "voice_enabled": True}, {"name": "B", "greeting": "Hi there", "cta_text": None, "accent_color": "", "voice_enabled": False},
               {"name": "Ünï", "greeting": None, "cta_text": "", "accent_color": None, "voice_enabled": None}]:
    T["view"].append({"tenant": tenant, "out": tenants.public_view(tenant)})
out["tenants"] = T

json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"))
