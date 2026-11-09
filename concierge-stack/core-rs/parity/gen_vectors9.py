"""Batch-9 golden vectors: SMS signatures/sender rules and the RAG prompt/URL helpers, from the live modules.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors9.py > ../concierge-stack/core-rs/parity/vectors9.json
"""
import base64
import hashlib
import hmac
import json
import os
import random
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import rag, sms  # noqa: E402

rng = random.Random(20261117)
UTC = timezone.utc

# ---- Twilio signature -------------------------------------------------------------------------------------------
def twilio_sig(token, url, params):
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


twilio_cases = []
for token in ("tok-123", "é-token"):
    for url in ("https://chat.example.test/api/v1/sms/twilio", "https://x.test/a?b=c"):
        for params in ({}, {"From": "+6421", "Body": "hi"}, {"b": "2", "a": "1", "B": "x", "é": "ü", "Z": ""}):
            good = twilio_sig(token, url, params)
            for sig in (good, good[:-1] + ("A" if good[-1] != "A" else "B"), "", good.lower() if good.lower() != good else good + "x", "x" * 28, good + " "):
                twilio_cases.append({"token": token, "url": url, "params": sorted(params.items(), key=lambda kv: rng.random()), "sig": sig, "out": sms.validate_signature(token, url, params, sig)})
twilio_cases.append({"token": "t", "url": "u", "params": [], "sig": None, "out": sms.validate_signature("t", "u", {}, None)})

# ---- gateway payload & signature ---------------------------------------------------------------------------------
payload_cases = [{"to": to, "body": b, "sim": sim, "out": sms.smsgate_payload(to, b, sim)} for to in ("+6421", "+15551234567") for b in ("hi", "é" * 1600, "x" * 1500, "")
                 for sim in (-1, 0, 1, 2, 3, 4)]
gate_cases = []
NOW = 1_800_000_000.0
for key in ("signing-key", "é-key"):
    for ts, bodyb in ((str(int(NOW)), b'{"a":1}'), (str(int(NOW) - 299), b""), (str(int(NOW) - 300), b"b1"), (str(int(NOW) + 300), b"b2"), (str(int(NOW) - 301), b"x"), (str(int(NOW) + 400), b"y"), (" " + str(int(NOW)) + " ", b"z"), ("abc", b"q"), ("", b"q"), (str(int(NOW)), "é".encode())):
        mac = hmac.new(key.encode(), bodyb + ts.encode(), hashlib.sha256).hexdigest()
        for sig in (mac, mac.upper(), " " + mac + " ", mac[:-1] + "0", "", "zz"):
            for tol in (300, 10):
                gate_cases.append({"key": key, "body_hex": bodyb.hex(), "ts": ts, "sig": sig, "now": NOW, "tol": tol, "out": sms.validate_smsgate_signature(key, bodyb, ts, sig, NOW, tol)})
gate_cases.append({"key": "", "body_hex": "", "ts": str(int(NOW)), "sig": "x", "now": NOW, "tol": 300, "out": sms.validate_smsgate_signature("", b"", str(int(NOW)), "x", NOW, 300)})

ready_cases = []
for provider in (None, "", "none", "TWILIO", " twilio ", "smsgate", "bogus"):
    for sid in ("", "AC1"):
        for tok in ("", "tk"):
            for msid in ("", "MG1"):
                for frm in ("", "+1555"):
                    for tfrom in ("", "+1666"):
                        s = SimpleNamespace(sms_provider=provider, twilio_account_sid=sid, twilio_auth_token=tok, twilio_messaging_service_sid=msid, twilio_from_number=tfrom,
                                            smsgate_base_url="http://gw", smsgate_username="u", smsgate_password="p")
                        sms.get_settings = lambda s=s: s
                        tenant = rng.choice([None, {}, {"sms_from": frm}, {"sms_transport": "device", "sms_enabled": bool(frm), "sms_from": frm}, {"sms_transport": "device", "sms_enabled": True, "sms_from": frm}])
                        ready_cases.append({"provider": provider, "sid": sid, "tok": tok, "msid": msid, "tfrom": tfrom, "tenant": tenant, "out": sms.sender_ready(tenant)})
for base, user, pw in (("", "u", "p"), ("http://gw", "", "p"), ("http://gw", "u", ""), ("http://gw", "u", "p")):
    s = SimpleNamespace(sms_provider="smsgate", twilio_account_sid="", twilio_auth_token="", twilio_messaging_service_sid="", twilio_from_number="", smsgate_base_url=base, smsgate_username=user, smsgate_password=pw)
    sms.get_settings = lambda s=s: s
    ready_cases.append({"provider": "smsgate", "sid": "", "tok": "", "msid": "", "tfrom": "", "tenant": None, "gate": [base, user, pw], "out": sms.sender_ready(None)})

# ---- rag --------------------------------------------------------------------------------------------------------
URLS = ["https://x.test/a", "http://x.test", "https://x.test/p?utm_source=mine&a=1", "https://x.test/p?a=1&a=2&b=&c", "https://x.test/p?q=a+b%20c&r=%E3%81%82", "https://x.test/p?x=%zz&y=%",
        "https://x.test/p#frag", "https://x.test/p?a=1#frag", "https://x.test:8443/p/q.html", "https://user:pw@x.test/p", "https://x.test", "https://x.test?a=b", "https://x.test/p?&&a=1&&",
        "ftp://x.test/p", "mailto:a@b.co", "/relative/path", "", "https://[::1]/p", "https://[::1/p", "HTTPS://x.test/", "https://x.test/p?utm_medium=email", "https://x.test/pa th?k=v w",
        "https://x.test/é?ü=ñ", "https://x.test/p?a=%F0%9F%98%80&b=%FF", "https://x.test/a\tb"]
tag_cases = []
for u in URLS:
    for ch in ("chat", "voice", "sms", "é"):
        try:
            out = rag.tag_url(u, ch)
        except ValueError:
            out = None
        tag_cases.append({"url": u, "ch": ch, "out": out})

HOURS = [None, {}, {"mon": [["09:00", "17:00"]], "tue": [["09:00", "12:00"], ["13:00", "17:00"]], "sat": []}, {"sun": [["10:00", "14:00"]], "wed": None}]
FIXED = datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC)


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


rag.datetime = FixedDT
HITS = [None, [], [{"title": "Hours", "url": "https://x.test/hours", "content": "We open at 9."}, {"title": "", "url": "https://x.test/p?a=1", "content": "Price list\nline2"}, {"title": None, "url": "http://x.test", "content": "é"}]]
prompt_cases = []
for _ in range(160):
    tenant = {"name": rng.choice(["Trendi", "Café Ünï"]), "persona": rng.choice([None, "", "  Friendly and brief.  ", "Speak like a pirate\nArr"]),
              "incentive": rng.choice([None, "", " 10% off this week "]), "native_booking": rng.choice([None, False, True]), "booking_url": rng.choice([None, "", "https://x.test/book"]),
              "timezone": rng.choice([None, "", "UTC", "Pacific/Auckland", "America/New_York"]), "business_hours": rng.choice(HOURS)}
    hits, channel = rng.choice(HITS), rng.choice(["chat", "voice", "sms"])
    prompt_cases.append({"tenant": tenant, "hits": hits, "ch": channel, "now": int(FIXED.timestamp()), "out": rag.build_system_prompt(tenant, hits, channel)})

print(json.dumps({"twilio": twilio_cases, "payload": payload_cases, "gate": gate_cases, "ready": ready_cases, "tag": tag_cases, "prompt": prompt_cases}, ensure_ascii=False, indent=0, default=str))
