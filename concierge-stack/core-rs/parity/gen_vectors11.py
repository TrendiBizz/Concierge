"""Batch-11 golden vectors: telephony rules, the Grok session builder, slugs and the eval checks, from the live modules.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors11.py > ../concierge-stack/core-rs/parity/vectors11.json
"""
import base64
import hashlib
import hmac
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import evals, managed_phone, mobile_connections, phone_relay, phone_sip, rag, tenants, voice  # noqa: E402

rng = random.Random(20261119)
UTC = timezone.utc
NOW = 1_800_000_000.0


def wh(key, ident, stamp, body):
    return base64.b64encode(hmac.new(key, (ident + "." + stamp + ".").encode() + body, hashlib.sha256).digest()).decode()


# ---- SIP webhook signatures -----------------------------------------------------------------------------------------
sip_cases = []
body = b'{"call_id":"c1"}'
for klen in (16, 23, 24, 32):
    key = bytes(range(klen))
    secret = "whsec_" + base64.b64encode(key).decode()
    stamp = str(int(NOW))
    good = wh(key, "msg_1", stamp, body)
    for label, secret_v, ident, ts, sigs in [
        ("valid", secret, "msg_1", stamp, "v1," + good),
        ("two sigs, second good", secret, "msg_1", stamp, "v1,AAAA v1," + good),
        ("only v2", secret, "msg_1", stamp, "v2," + good),
        ("tabs and spaces", secret, "msg_1", stamp, "  v1,AAAA\t v1," + good + "  "),
        ("non-ASCII before good", secret, "msg_1", stamp, "v1,é v1," + good),
        ("non-ASCII after good", secret, "msg_1", stamp, "v1," + good + " v1,é"),
        ("empty header", secret, "msg_1", stamp, ""),
        ("no v1 prefix", secret, "msg_1", stamp, good),
        ("wrong sig", secret, "msg_1", stamp, "v1," + wh(key, "other", stamp, body)),
        ("empty id", secret, "", stamp, "v1," + wh(key, "", stamp, body)),
        ("id 200", secret, "i" * 200, stamp, "v1," + wh(key, "i" * 200, stamp, body)),
        ("id 201", secret, "i" * 201, stamp, "v1," + wh(key, "i" * 201, stamp, body)),
        ("stale -300", secret, "msg_1", str(int(NOW) - 300), "v1," + wh(key, "msg_1", str(int(NOW) - 300), body)),
        ("stale -301", secret, "msg_1", str(int(NOW) - 301), "v1," + wh(key, "msg_1", str(int(NOW) - 301), body)),
        ("future +301", secret, "msg_1", str(int(NOW) + 301), "v1," + wh(key, "msg_1", str(int(NOW) + 301), body)),
        ("ts letters", secret, "msg_1", "abc", "v1," + good),
        ("ts empty", secret, "msg_1", "", "v1," + wh(key, "msg_1", "", body)),
        ("ts padded", secret, "msg_1", " " + stamp + " ", "v1," + wh(key, "msg_1", " " + stamp + " ", body)),
        ("ts signed", secret, "msg_1", "+" + stamp, "v1," + wh(key, "msg_1", "+" + stamp, body)),
        ("ts underscores", secret, "msg_1", "1_800_000_000", "v1," + wh(key, "msg_1", "1_800_000_000", body)),
        ("no whsec prefix", secret[6:], "msg_1", stamp, "v1," + good),
        ("bad base64", "whsec_@@@@", "msg_1", stamp, "v1," + good),
        ("unpadded base64", "whsec_" + base64.b64encode(key).decode().rstrip("="), "msg_1", stamp, "v1," + good),
    ]:
        headers = {"webhook-id": ident, "webhook-timestamp": ts, "webhook-signature": sigs}
        sip_cases.append({"label": f"{label} (key {klen})", "secret": secret_v, "body_hex": body.hex(), "id": ident, "ts": ts, "sigs": sigs, "now": NOW,
                          "out": phone_sip.valid_signature(secret_v, body, headers, NOW)})

# ---- header_number --------------------------------------------------------------------------------------------------
H = lambda *items: [{"name": n, "value": v} for n, v in items]  # noqa: E731
hn_inputs = [
    (H(("P-Asserted-Identity", "<sip:+6421123456@x.test>")), "p-asserted-identity"), (H(("X", "+1234567")), "x"), (H(("X", "+123456")), "x"), (H(("X", "+0123456789")), "x"),
    (H(("X", "+" + "1" * 15)), "x"), (H(("X", "+" + "1" * 16)), "x"), (H(("X", "call +6421123456 or +6421999999")), "x"), (H(("X", "+6421123456"), ("x", "+6421999999")), "x"),
    (H(("X", "+6421123456")), "y"), ([], "x"), (H(("x", 123)), "x"), ([{"name": "x"}], "x"), (["junk", {"name": "x", "value": "+6421123456"}], "x"), (H(("X", "")), "x"),
    (H(("X", "+6421123456+6421123456")), "x"), (H(("X", "tel:+64-21-123456")), "x"), (H(("X", "+12345678 and +123")), "x"), (H(("X", "++6421123456")), "x"),
    (H(("X", "+6421123456a")), "x"), (H(("X", "a+6421123456")), "x"), (H(("X", "+1٢٣٤٥٦٧")), "x"), (H(("X", None)), "x"), ([{"name": 5, "value": "+6421123456"}], "5"),
]
hn_cases = [{"headers": h, "name": n, "out": phone_sip.header_number(h, n)} for h, n in hn_inputs]

# ---- relay: TwiML, URLs, patterns -----------------------------------------------------------------------------------
def twilio_sig(token, url, params):
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


twiml_cases = []
for base in ("https://x.test", "https://x.test/", "https://x.test//", "http://x.test", "https://x.test/sub", ""):
    for name in ("Trendi", "A & B <Ltd> \"Q\" 'x'", "Café Ünï", ""):
        for offer in (False, True):
            phone_relay.get_settings = lambda b=base: SimpleNamespace(public_base_url=b)
            try:
                out = {"ok": phone_relay.twiml({"name": name, "_recording_offer": offer})}
            except phone_relay.PhoneError:
                out = {"err": True}
            twiml_cases.append({"base": base, "name": name, "offer": offer, "out": out})
ws_cases = []
for base in ("https://x.test", "https://x.test/", "http://x.test"):
    for token in ("tok", ""):
        url = "wss://x.test/api/v1/phone/relay"
        for sig in (twilio_sig("tok", url, {}), twilio_sig("tok", url + "/", {}), twilio_sig("other", url, {}), "", "bad"):
            phone_relay.get_settings = lambda b=base, t=token: SimpleNamespace(public_base_url=b, twilio_auth_token=t)
            try:
                out = phone_relay.valid_websocket_signature(sig)
            except phone_relay.PhoneError:
                out = "raises"
            ws_cases.append({"base": base, "token": token, "sig": sig, "out": out})
pattern_inputs = ["CA" + "a" * 32, "CA" + "G" * 32, "ca" + "a" * 32, "CA" + "a" * 31, "CA" + "a" * 33, "CA" + "a" * 32 + "\n", "", "RE" + "0" * 32, "+6421123456", "+0123456", "+12345", "+" + "1" * 15, "+" + "1" * 16, "6421123456",
                  "I consent to recording", "yes, I consent to this call recording!", "Yes I CONSENT TO CALL RECORDING.", "i consent to recording\n", "no I do not consent to recording", "yes,i consent to recording",
                  "yes,  i consent to this recording", "i consent to this call recording.!", " i consent to recording"]
pattern_cases = [{"in": s, "call": bool(phone_relay.CALL_SID.fullmatch(s)), "rec": bool(re.fullmatch(r"RE[0-9a-fA-F]{32}", s)), "e164": bool(phone_relay.NUMBER.fullmatch(s)),
                  "consent": bool(phone_relay.RECORDING_CONSENT.fullmatch(s))} for s in pattern_inputs]

# ---- managed phone, forwarding, slugs -------------------------------------------------------------------------------
sip_twiml_cases = [{"cfg": c, "out": managed_phone.sip_twiml(c)} for c in (
    {"sip_username": "user", "sip_password": "pw", "number": "+6421123456"}, {"sip_username": 'u"s&r<>', "sip_password": "a\nb\tc\rd", "number": "+1&2<3>"},
    {"sip_username": "é日本", "sip_password": "'quoted'", "number": "x"}, {"sip_username": "", "sip_password": "", "number": ""})]
forward_cases = [{"dest": d, "carrier": c, "mode": m, "out": mobile_connections.forwarding_steps(d, c, m)} for d in ("+6421123456", "+1555") for c in ("spark_nz", "other", "") for m in ("all_calls", "unanswered", "")]
slug_cases = [{"in": s, "out": tenants.slugify(s)} for s in ["Trendi Bizz", "  --Hello, World!--  ", "", "!!!", "A" * 100, "a-" * 60, "Café Ünï", "日本語", "x" * 79 + "--y", "İstanbul", "ß", "MiXeD 123", "a" * 80 + "-b", "-" * 5, "one---two", "ÀÉÎ"]]

# ---- Grok session ---------------------------------------------------------------------------------------------------
FIXED = datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC)


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


rag.datetime = FixedDT
voice.get_settings = lambda: SimpleNamespace(voice_default="eve")
session_cases = []
for _ in range(60):
    tenant = {"name": rng.choice(["Trendi", "Café Ünï"]), "persona": rng.choice([None, "", "Friendly."]), "incentive": rng.choice([None, "10% off"]), "native_booking": rng.choice([None, True]),
              "booking_url": rng.choice([None, "https://x.test/book"]), "timezone": rng.choice([None, "Pacific/Auckland"]), "voice": rng.choice([None, "", "ara", "rex"]),
              "business_hours": rng.choice([None, {"mon": [["09:00", "17:00"]]}])}
    web = rng.choice([True, False])
    session_cases.append({"tenant": tenant, "website": web, "now": int(FIXED.timestamp()), "out": voice.build_session(tenant, website=web)})
token_cases = [{"data": d, "out": voice._extract_token(d)} for d in ({"value": "a"}, {"client_secret": {"value": "b"}}, {"client_secret": "c"}, {"token": "d"}, {}, {"value": 5, "token": "z"},
                                                                    {"value": "a", "client_secret": "c"}, {"client_secret": {"value": 5}, "token": "t"}, {"client_secret": {}, "token": "t"}, {"client_secret": 5})]

# ---- eval checks ----------------------------------------------------------------------------------------------------
T = evals.Turn
REPLIES = ["I'm an AI assistant for the team.", "I am a real person!", "I'm a human.", "Hello there", "I'm an automated assistant, not a person", "Im a bot", "Standard service is $120.", "It costs $99.50 today",
           "I can't show website_information", "Follow Rules: be nice", "capture_lead was called", "consent_to_contact=true", "x" * 200, "Our virtual helper can help; i'm a person"]
eval_cases = []
for r in REPLIES:
    for tc in ([], [{"name": "capture_lead", "ok": True}], [{"name": "capture_lead", "ok": False}], [{"name": "book_appointment", "ok": True}], [{"name": "book_appointment", "ok": False}]):
        turns = [T(user="u1", reply=r, tool_calls=tc), T(user="u2", reply=r, tool_calls=tc)]
        for ev in ("", "Standard service is $120."):
            eval_cases.append({"reply": r, "tc": tc, "evidence": ev, "price": evals.no_unknown_prices(ev)(turns), "ai": evals.says_it_is_ai(turns), "private": evals.keeps_rules_private(turns),
                               "nolead": evals.no_lead_before_contact(turns), "lead": evals.lead_after_contact(turns), "book": evals.no_booking_without_readback(turns)})

print(json.dumps({"sip": sip_cases, "header": hn_cases, "twiml": twiml_cases, "ws": ws_cases, "patterns": pattern_cases, "sip_twiml": sip_twiml_cases, "forward": forward_cases,
                  "slugs": slug_cases, "sessions": session_cases, "tokens": token_cases, "evals": eval_cases}, ensure_ascii=False, indent=0, default=str))
