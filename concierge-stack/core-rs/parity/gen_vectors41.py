"""Batch-41 golden vectors for the owner-portal reads: the session header rule (`owner_auth.current_user`), the onboarding overview
(`owner_onboarding.overview`) and the readiness report (`main.owner_channel_readiness`).

Every expected value is the output of the LIVE function. Only its inputs are stubbed: the tenant row (`tenants.get_by_id`), the
database (`db.pool()`: phone numbers, the paired SMS phone, channel declarations, and the session lookup), `datetime.now` and
the settings (a real `config.Settings` built from keyword arguments, so `effective_llm_key`, `email_configured` and
`sms_configured` are the real properties). A function that raises is recorded as `"error": <kind>`.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors41.py > ../concierge-stack/core-rs/parity/vectors41.json
"""
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from fastapi import HTTPException  # noqa: E402

from app import channel_authorization, config, main, owner_auth, owner_onboarding, phone_relay, phone_sip, tenants  # noqa: E402

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
rng = random.Random(20261140)


class FakeDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class Pool:
    def __init__(self, numbers=(), device=None, declarations=(), session=None):
        self.numbers, self.device, self.declarations, self.session = list(numbers), device, list(declarations), session
        self.digest = None

    async def fetch(self, sql, *args):
        if "FROM phone_numbers" in sql:
            return [dict(e164=e, enabled=en) for e, en in self.numbers]
        if "FROM tenant_channel_authorizations" in sql:
            return [dict(channel=c, authorized=a, updated_at=NOW) for c, a in self.declarations]
        raise AssertionError(sql)

    async def fetchrow(self, sql, *args):
        if "FROM sms_devices" in sql:
            return self.device
        if "FROM tenant_sessions" in sql:
            self.digest = args[0]
            return self.session
        raise AssertionError(sql)


def settings(**kw):
    return config.Settings(_env_file=None, **kw)


def install(pool, tenant, s):
    async def get_by_id(_):
        return tenant

    tenants.get_by_id = get_by_id
    for module in (owner_onboarding, phone_relay, phone_sip, main):
        module.get_settings = lambda s=s: s
        if hasattr(module, "db"):
            module.db.pool = lambda pool=pool: pool
    owner_onboarding.db.pool = lambda: pool
    channel_authorization.db.pool = lambda: pool
    import datetime as dt
    dt.datetime = FakeDT  # `from datetime import datetime` inside overview() resolves this attribute at call time


def outcome(coro):
    try:
        return {"out": asyncio.run(coro)}
    except ValueError:
        return {"error": "ValueError"}
    except HTTPException as e:
        return {"error": "http", "status": e.status_code, "detail": e.detail}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


def jsonable(v):
    return json.loads(json.dumps(v, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)))


# ------------------------------------------------------------------ the session header rule
header_cases = []
HEADERS = ["", "Bearer", "Bearer ", "Bearer x", "bearer x", "BEARER x", "BeArEr x", "Basic x", "x", "Bearer  x", "Bearer x ", "Bearer a b", " Bearer x", "Bearer\tx",
           "Bearer " + "a" * 256, "Bearer " + "a" * 257, "Bearer " + "é" * 256, "Bearer " + "é" * 257, "Bearer é", "bearer İ", "Bearer 日本語", "Bearer  x", "ＢＥＡＲＥＲ x",
           "Bearer x\ty", "Bearer " + "\x7f", "Kearer x", "Bearer x"]
for h in HEADERS:
    pool = Pool()
    owner_auth.db.pool = lambda pool=pool: pool
    r = outcome(owner_auth.current_user(h))
    header_cases.append({"header": h, "reached_db": pool.digest is not None, "digest": pool.digest, **r})

# ------------------------------------------------------------------ onboarding overview and readiness
TENANT_SHAPES = [
    {}, {"slug": "t-one", "name": "One <Co>", "site_url": "https://one.example", "greeting": "Hi", "voice_enabled": True, "native_booking": True, "slot_minutes": 45,
         "business_hours": {"mon": [["09:00", "17:00"]]}, "email_auto_reply": True, "notify_phone": "+64211234567", "notify_email": "o@x.invalid", "timezone": "Europe/Paris",
         "phone_enabled": True, "sms_enabled": True, "sms_transport": "device"},
    {"slug": "t-two", "name": "", "site_url": None, "greeting": None, "voice_enabled": False, "native_booking": None, "business_hours": {}, "timezone": "", "phone_enabled": False,
     "sms_enabled": True, "sms_transport": ""},
    {"slug": " t-three ", "name": "Ünï", "site_url": "", "voice_enabled": 1, "slot_minutes": 0, "email_auto_reply": 0, "notify_email": "", "notify_phone": None, "timezone": None,
     "phone_enabled": 1, "sms_enabled": 0, "sms_transport": "device"},
    {"slug": "t-four", "name": "Four", "site_url": "https://f.example", "voice_enabled": True, "phone_enabled": True, "sms_enabled": True, "sms_transport": "device",
     "notify_email": "four@x.invalid", "business_hours": {"tue": []}},
]
SIPID = "11111111-2222-4333-8444-555555555555"
SIP_VALUES = ["", "{}", "not json", "[]", "[1]", "5", "null", '"abc"', "{" + f'"{SIPID}": 5' + "}",
              json.dumps({SIPID: {"enabled": True, "tenant": "t-one", "number": "+6499000001", "signing_secret": "whsec_x"}}),
              json.dumps({SIPID: {"enabled": True, "tenant": "t-two", "number": "+6499000001", "signing_secret": "whsec_x"}}),
              json.dumps({SIPID: {"enabled": False, "tenant": "t-one", "number": "+6499000001", "signing_secret": "whsec_x"}}),
              json.dumps({SIPID: {"enabled": True, "tenant": "t-one", "number": "+6499000001"}}),
              json.dumps({SIPID: {"enabled": True, "tenant": "t-one", "number": "+6499000009", "signing_secret": "s"}}),
              json.dumps({SIPID.upper(): {"enabled": True, "tenant": "t-one", "number": "+6499000001", "signing_secret": "s"}}),
              json.dumps({"bad-id": {"enabled": True, "tenant": "t-one", "number": "+6499000001", "signing_secret": "s"}}),
              json.dumps({SIPID.replace("-", ""): {"enabled": True, "tenant": "t-one", "number": "+6499000001", "signing_secret": "s"}}),
              json.dumps({SIPID: {"enabled": 1, "tenant": "t-one", "number": "+6499000001", "signing_secret": "s"}}),
              json.dumps({"x": {}, SIPID: {"enabled": True, "tenant": "t-one", "number": "+6499000001", "signing_secret": "s"}})]
NUMBER_SETS = [[], [("+6499000001", True)], [("+6499000001", False)], [("+6499000002", True), ("+6499000001", False)], [("+6499000001", True), ("+6499000002", True)]]


def device(kind):
    if kind == 0:
        return None
    last = {1: NOW - timedelta(seconds=10), 2: NOW - timedelta(seconds=299), 3: NOW - timedelta(seconds=300), 4: NOW - timedelta(seconds=301), 5: None,
            6: NOW + timedelta(seconds=500), 7: NOW - timedelta(seconds=299, microseconds=999999), 8: NOW - timedelta(days=2)}[kind]
    return {"last_seen": last, "verified_at": NOW if rng.random() < .6 else None, "inbound_verified_at": NOW if rng.random() < .6 else None}


def rand_settings():
    kw = {}
    pick = rng.choice
    if rng.random() < .6:
        kw["llm_api_key"] = pick(["", "k", "key"])
    if rng.random() < .5:
        kw["xai_api_key"] = pick(["", "x"])
    kw["website_verified_tenants"] = pick(["", "t-one", " t-one , t-two", "t-three", "t-one,,t-four", " "])
    kw["phone_verified_tenants"] = pick(["", "t-one", "t-one, t-four", " t-two "])
    kw["phone_receptionist_enabled"] = pick([True, False])
    kw["phone_voice_provider"] = pick(["grok", "legacy_twilio_tts"])
    kw["xai_sip_connections"] = pick(SIP_VALUES)
    kw["twilio_auth_token"] = pick(["", "tok"])
    kw["twilio_account_sid"] = pick(["", "AC1"])
    kw["twilio_from_number"] = pick(["", "+15550001111"])
    kw["twilio_messaging_service_sid"] = pick(["", "MG1"])
    kw["public_base_url"] = pick(["http://localhost:8000", "https://c.example", "https://"])
    kw["sms_provider"] = pick(["twilio", "smsgate", "none", "", " TWILIO ", "other"])
    kw["smsgate_base_url"] = pick(["", "https://sms.invalid"])
    kw["smsgate_username"] = pick(["", "u"])
    kw["smsgate_password"] = pick(["", "p"])
    kw["smtp_host"] = pick(["", "smtp.invalid"])
    kw["smtp_from"] = pick(["", "f@x.invalid"])
    kw["social_service_enabled"] = pick([True, False])
    kw["voice_recording_enabled"] = pick([True, False])
    kw["phone_recording_enabled"] = pick([True, False])
    kw["inbound_cloudflare_enabled"] = pick([True, False])
    return kw


overview_cases = []
for i in range(420):
    tenant = dict(rng.choice(TENANT_SHAPES))
    numbers = rng.choice(NUMBER_SETS)
    kind = rng.choice([0, 0, 1, 1, 2, 3, 4, 5, 6, 7, 8])
    dev = device(kind)
    kw = rand_settings()
    decl = rng.sample(sorted(channel_authorization.CHANNELS), rng.randint(0, 5))
    declarations = [(c, rng.random() < .5) for c in decl]
    s = settings(**kw)
    pool = Pool(numbers, dev, declarations)
    install(pool, tenant, s)
    case = {"tenant": tenant, "numbers": numbers, "settings": kw, "declarations": declarations,
            "device": None if dev is None else {"last_seen": dev["last_seen"].timestamp() if dev["last_seen"] else None, "verified": dev["verified_at"] is not None,
                                                "inbound_verified": dev["inbound_verified_at"] is not None},
            "now": NOW.timestamp()}
    if tenant:
        ov = outcome(owner_onboarding.overview("tid"))
        rd = outcome(main.owner_channel_readiness({"tenant_id": "tid"}))
    else:
        ov = outcome(owner_onboarding.overview("tid"))
        rd = outcome(main.owner_channel_readiness({"tenant_id": "tid"}))
    case["overview"] = jsonable(ov)
    case["readiness"] = jsonable(rd)
    overview_cases.append(case)

print(json.dumps({"headers": header_cases, "cases": overview_cases}, ensure_ascii=False, indent=0))
