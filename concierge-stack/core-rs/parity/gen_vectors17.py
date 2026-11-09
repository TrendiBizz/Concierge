"""Batch-17 golden vectors: the HTTP request models and small helpers of `main.py`, from the live module.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors17.py > ../concierge-stack/core-rs/parity/vectors17.json

Only the model classes and pure helpers are exercised: no route runs, no request is made, nothing is sent.
"""
import json
import os
import random
import sys
import uuid

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from pydantic import ValidationError  # noqa: E402

from app import main  # noqa: E402

rng = random.Random(20261124)
U = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
S = ["", "x", "Hello", "é" * 3, "a b", " pad ", "tab\t", "line\nbreak", "😀"]
BAD = [None, 5, 1.5, True, [], {}, ["a"], {"a": "b"}]


def lens(n):
    return ["z" * n, "z" * (n - 1), "z" * (n + 1)] if n > 1 else ["z" * n, "z" * (n + 1)]


def str_opts(mn=0, mx=None, pat=None):
    o = list(S) + BAD
    if mx:
        o += lens(mx)
    if mn > 1:
        o += lens(mn)
    return o


UTM = [{}, {"utm_source": "g"}, {"utm_source": 5}, {"a": None}, "x", [1], {"k": "é"}, None]
DT = [None, "2026-11-09T01:02:03+00:00", "2026-11-09T01:02:03-00:00", "2026-11-09T01:02:03Z", "2026-11-09T01:02:03", "2026-11-09T14:02:03+13:00", "2026-11-09T01:02:03-05:30", "2026-11-09", "2026-13-09T01:02:03Z",
      "2026-11-09T25:02:03Z", "garbage", "", 1700000000, True, [1], "2026-02-30T00:00:00Z"]
INTS = lambda lo, hi: [lo, hi, lo - 1, hi + 1, (lo + hi) // 2, str(lo), str(hi), " 5 ", "5.0", "5.", "5.00", "5.50", 5.0, 5.5, True, False, None, "x", [], {}, "1_0", "_1", 10**20, -1, 0]  # noqa: E731
BOOLS = [True, False, None, "true", "no", 1, 0, 2, "maybe", 1.0, 1.5, [], "ON"]
HOURS = [None, {}, {"mon": [["09:00", "17:00"]]}, {"funday": []}, {"mon": [["17:00", "09:00"]]}, {"mon": [["09:00", "09:00"]]}, {"mon": [["9:00", "17:00"]]},
         {"mon": [["09:00"]]}, {"mon": [["09:00", "10:00"], ["09:30", "11:00"]]}, {"mon": "x"}, {"mon": [5]}, {"mon": [["09:00", 5]]}, [1], 5, {"mon": [["09:00", "17:00\n"]]},
         {d: [] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "mon2"]}, {"mon": [["24:00", "25:00"]]}, {"sun": [["00:00", "23:59"]] * 6}]
SCORING = [None, {}, {"warm_at": 10}, {"hot_at": 40, "warm_at": 20}, {"warm_at": 90, "hot_at": 80}, {"nope": 1}, {"warm_at": "20"}, {"warm_at": True}, {"warm_at": 1000},
           {"warm_at": 20.0}, {"warm_at": 20.5}, [1], 5, {"warm_at": None}]
TZ = [None, "UTC", "America/Chicago", "Nope/Zone", "", "utc", "../x", 5]
TEMPLATES = [None, "Hi {first}", "Hi {first} from {business} ({name})", "{unknown}", "{", "}", "{}", "{0}", "{first!r}", "{first!x}", "{first:>5}", "{first.upper}", "{first[0]}",
             "{{literal}}", "plain", "", "{first!s}", "{name!a}", "{ first }", 5]
UUIDS = [U, U.upper(), U.replace("-", ""), "{" + U + "}", "urn:uuid:" + U, "not-a-uuid", "", None, 5, U[:-1], U + "0", " " + U, "g" * 36]


EXTRA = {"E164": ["+64211234567", "+6421123", "+0211234567", "+64211234567\n", "64211234567", "+٦٤٢١١٢٣٤٥٦٧", "+" + "1" * 15, "+" + "1" * 16],
         "RID": [U, U.upper(), "a" * 36, "-" * 36, "g" * 36, U[:-1], U.replace("-", "0")],
         "^[A-Za-z0-9_.-]+$": ["ok-label_1.2", "bad label", "é", "a/b", "A" * 80]}


def opts(spec):
    k = spec[0]
    if k == "str":
        return str_opts(*spec[1:]) + EXTRA.get(spec[3] if len(spec) > 3 else None, [])
    if k == "int":
        return INTS(spec[1], spec[2])
    if k == "bool":
        return BOOLS
    if k == "lit":
        return list(spec[1]) + ["nope", "", None, 5, spec[1][0].upper(), [spec[1][0]]]
    if k == "true":
        return [True, False, 1, 0, 2, 1.0, "true", None, "yes", [True]]
    if k == "list":
        return [[], ["a"], ["a", "b"], ["a"] * spec[1], ["a"] * (spec[1] + 1), ["a", 5], "a", None, {}, 5, [[]]]
    if k == "listlit":
        return [[], list(spec[1]), [spec[1][0]], ["nope"], [spec[1][0], 5], "x", None, [spec[1][0]] * 3]
    if k == "dictstr":
        return UTM
    if k == "dict":
        return [{}, {"a": 1}, {"a": {"b": [1]}}, [], "x", None, 5]
    if k == "uuid":
        return UUIDS
    if k == "dt":
        return DT
    if k == "hours":
        return HOURS
    if k == "scoring":
        return SCORING
    if k == "tz":
        return TZ
    if k == "tpl":
        return TEMPLATES
    raise KeyError(k)


ST = ("lit", ["new", "contacted", "booked", "won", "lost"])
MODELS = {
    "ChatRequest": {"key": ("str", 1), "session_id": ("str", 1), "message": ("str", 1, 1000), "page_url": ("str",), "utm": ("dictstr",)},
    "VoiceTokenRequest": {"key": ("str",), "session_id": ("str",), "recording_consent": ("bool",)},
    "ToolRequest": {"key": ("str",), "session_id": ("str",), "args": ("dict",), "page_url": ("str",), "utm": ("dictstr",), "voice_session_id": ("uuid",), "voice_session_token": ("str", 0, 200)},
    "VoiceLogRequest": {"key": ("str",), "session_id": ("str",), "role": ("lit", ["user", "assistant"]), "text": ("str", 1, 4000), "page_url": ("str",), "utm": ("dictstr",)},
    "TenantCreate": {"name": ("str",), "site_url": ("str",), "slug": ("str",), "persona": ("str",), "greeting": ("str",), "booking_url": ("str",), "lead_webhook_url": ("str",),
                     "incentive": ("str",), "allowed_origins": ("list", 3)},
    "TenantUpdate": {"name": ("str",), "site_url": ("str",), "allowed_origins": ("list", 3), "persona": ("str",), "greeting": ("str",), "cta_text": ("str",), "accent_color": ("str",),
                     "voice": ("str",), "voice_enabled": ("bool",), "phone_enabled": ("bool",), "phone_daily_limit": ("int", 0, 100000), "voice_daily_limit": ("int", 0, 100000),
                     "booking_url": ("str",), "lead_webhook_url": ("str",), "incentive": ("str",), "timezone": ("tz",), "business_hours": ("hours",), "slot_minutes": ("int", 5, 240),
                     "min_notice_hours": ("int", 0, 720), "max_days_ahead": ("int", 1, 365), "native_booking": ("bool",), "notify_email": ("str",), "sms_enabled": ("bool",),
                     "sms_from": ("str",), "lead_sms_template": ("tpl",), "review_url": ("str",), "lead_value_cents": ("int", 0, 100000000), "sla_minutes": ("int", 0, 1440),
                     "sla_min_score": ("int", 0, 100), "campaigns_enabled": ("bool",), "weekly_digest": ("bool",), "scoring": ("scoring",)},
    "CloneRequest": {"name": ("str",), "site_url": ("str",), "slug": ("str",)},
    "LeadUpdate": {"status": ST, "notes": ("str", 0, 4000), "value_cents": ("int", 0, 100000000), "lost_reason": ("str", 0, 300), "next_action_at": ("dt",)},
    "AppointmentUpdate": {"status": ("lit", ["booked", "completed", "cancelled", "no_show"])},
    "CrawlRequest": {"max_pages": ("int", 1, 300)},
    "IngestTextRequest": {"label": ("str", 1, 80, "^[A-Za-z0-9_.-]+$"), "title": ("str",), "text": ("str", 1, 200000)},
    "CampaignCreate": {"name": ("str", 1, 120), "channel": ("lit", ["sms", "email"]), "subject": ("str", 0, 200), "body": ("str", 1, 600), "older_than_days": ("int", 0, 3650),
                       "statuses": ("listlit", ["new", "contacted", "booked", "won", "lost"]), "min_score": ("int", 0, 100), "max_recipients": ("int", 1, 10**9)},
    "CampaignSend": {"expected_recipients": ("int", 0, 10**6)},
    "MarketingConsent": {"consent": ("bool",), "basis": ("str", 5, 300)},
    "TaskCreate": {"title": ("str", 1, 200), "notes": ("str", 0, 2000), "due_at": ("dt",), "lead_id": ("str",)},
    "TaskUpdate": {"title": ("str", 0, 200), "notes": ("str", 0, 2000), "due_at": ("dt",), "status": ("lit", ["open", "done"])},
    "EmailDraftCreate": {"sender": ("str", 3, 320), "subject": ("str", 0, 250), "inbound_body": ("str", 1, 20000), "reply_body": ("str", 0, 10000), "source_id": ("str", 0, 500),
                         "generate": ("bool",)},
    "EmailDraftRevision": {"reply_body": ("str", 1, 10000)},
    "PhoneNumberCreate": {"e164": ("str", 0, None, "E164")},
    "PhoneNumberEnable": {"enabled": ("bool",)},
    "InboundMailbox": {"recipient": ("str", 3, 320), "enabled": ("bool",)},
    "OwnerInvite": {"email": ("str", 0, 320), "role": ("lit", ["viewer", "editor", "owner"])},
    "OwnerRecovery": {"email": ("str", 0, 320)},
    "OwnerRedeem": {"token": ("str", 20, 256), "password": ("str", 12, 256)},
    "OwnerLogin": {"slug": ("str",), "email": ("str",), "password": ("str",)},
    "VoiceCopyRequest": {"recipient": ("str", 1, 254), "channel": ("lit", ["sms", "email"]), "content": ("lit", ["text", "recording"]), "request_id": ("uuid",), "session_id": ("uuid",)},
    "PhoneSmsTest": {"acknowledgement": ("true",), "request_id": ("str", 36, None, "RID")},
    "OwnerSocialDraft": {"content": ("str", 1, 10000), "account_ids": ("list", 10), "link": ("str", 0, 2000), "hashtags": ("str", 0, 2000), "media": ("list", 10), "options": ("dict",)},
    "OwnerSocialCompose": {"content": ("str", 1, 10000), "account_ids": ("list", 10), "link": ("str", 0, 2000), "hashtags": ("str", 0, 2000), "media": ("list", 10), "options": ("dict",),
                           "video": ("str", 0, 2048)},
    "OwnerSocialSchedule": {"scheduled_at": ("int", 0, 4102444800)},
    "OwnerOAuthCallback": {"state": ("str", 32, 256), "code": ("str", 1, 2048)},
}
# valid values used to build mostly-valid bodies
out = {"models": {}, "helpers": {}}
for name, fields in MODELS.items():
    cls = getattr(main, name)
    cases = []
    def check(body):
        try:
            m = cls.model_validate(body)
            return {"ok": m.model_dump(mode="json")}
        except ValidationError as e:
            return {"errors": [[".".join(str(p) for p in err["loc"]), err["type"]] for err in e.errors()]}
        except Exception as e:  # noqa: BLE001
            return {"crash": type(e).__name__}

    # find, per field, the first option the model accepts when alone (others default / may be required: fill progressively)
    base = {}
    for f, spec in fields.items():
        for v in opts(spec):
            r = check({**base, f: v})
            if "errors" not in r or all(e[0] != f and not e[0].startswith(f + ".") for e in r["errors"]):
                if v is not None or True:
                    base[f] = v
                    if v is not None:
                        break
    # keep only fully valid base; fall back to whatever was discovered
    cases.append({"in": base, "out": check(base)})
    for f, spec in fields.items():
        for v in opts(spec):
            body = {**base, f: v}
            cases.append({"in": body, "out": check(body)})
        body = {k: x for k, x in base.items() if k != f}
        cases.append({"in": body, "out": check(body)})
    for _ in range(80):
        body = dict(base)
        for f in rng.sample(list(fields), rng.randint(1, min(4, len(fields)))):
            body[f] = rng.choice(opts(fields[f]))
        if rng.random() < 0.15:
            body["unexpected"] = rng.choice([1, "x"])
        cases.append({"in": body, "out": check(body)})
    for body in [{}, [], "x", None, 5]:
        cases.append({"in": body, "out": check(body)})
    out["models"][name] = cases

# helpers
H = out["helpers"]
H["origin"] = [{"in": u, "out": main._origin_of(u)} for u in ["https://Example.COM/a?b#c", "http://x.y:8080", "HTTPS://A.B", "http://localhost:8000/", "https://u:p@h.co/x"]]
H["money"] = [{"in": c, "out": main._money(c)} for c in [0, 1, 49, 50, 51, 99, 100, 149, 150, 151, 250, 12345, 99999999, 100000000, 123456789, -100, -50, -149, -150, 5, 250000, 1000000]]
H["twiml"] = [{"in": t, "out": main._twiml(t).body.decode()} for t in ["", "Hi", "a<b>&\"c'", "x" * 1600, "é\n", "]]>"]]
snippet_tenants = [{"slug": "acme", "public_key": "pk_1", "report_token": "rt_1", "calendar_token": "ct_1", "id": 1},
                   {"slug": "b", "public_key": "pk_2", "report_token": "rt_2", "calendar_token": None, "id": 2}]
H["snippet"] = []
for base in ["http://localhost:8000", "https://concierge.example.com"]:
    main.settings.public_base_url = base
    for t in snippet_tenants:
        H["snippet"].append({"base": base, "tenant": t, "out": main._with_snippet(t)})
H["campaign_view"] = [{"in": c, "out": main._campaign_view(c)} for c in [{"filters": '{"a": 1}'}, {"filters": {"a": 1}}, {"x": 1}, {"filters": None}, {"filters": "[]"}]]
H["audio"] = []
for mime in ["audio/wav", "audio/mpeg", "audio/webm;codecs=opus"]:
    r = main.private_audio_response({"audio": b"abc", "mime_type": mime}, "f." + mime.split("/")[1])
    H["audio"].append({"mime": mime, "headers": dict(r.headers), "body": r.body.decode("latin1")})

# origin allow-list decision (pure body of _tenant_for)
H["origin_gate"] = []
import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402


async def fake_get(key):
    return CUR["tenant"]


main.tenants.get_by_key = fake_get
for allowed in [[], ["https://a.com"], ["https://A.com/", "http://b.org"], ["https://a.com/path"]]:
    for origin in [None, "", "https://a.com", "https://A.COM/", "https://other.com", "http://localhost:8000", "https://a.com/path", "http://b.org"]:
        for base in ["http://localhost:8000", "https://concierge.example.com"]:
            main.settings.public_base_url = base
            CUR = {"tenant": {"allowed_origins": allowed}}
            req = SimpleNamespace(headers={"origin": origin} if origin is not None else {})
            try:
                asyncio.run(main._tenant_for(req, "k"))
                res = {"ok": True}
            except HTTPException as e:
                res = {"status": e.status_code, "detail": e.detail}
            H["origin_gate"].append({"allowed": allowed, "origin": origin, "base": base, "out": res})

# rate-limit decision order and messages
H["rate"] = []
for ip_ok in (True, False):
    for sess_ok in (True, False):
        for session in (None, "", "s1"):
            for client in (True, False):
                calls = []

                class L:
                    def __init__(s, name, ok):
                        s.name, s.ok = name, ok

                    def check(s, key):
                        calls.append([s.name, key])
                        return s.ok

                main.ip_limiter, main.session_limiter = L("ip", ip_ok), L("session", sess_ok)
                req = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4") if client else None)
                try:
                    main._rate_limit(req, session)
                    res = {"ok": True}
                except HTTPException as e:
                    res = {"status": e.status_code, "detail": e.detail}
                H["rate"].append({"ip_ok": ip_ok, "sess_ok": sess_ok, "session": session, "client": client, "out": res, "calls": calls})

json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
