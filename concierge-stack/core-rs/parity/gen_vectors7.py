"""Batch-7 golden vectors: sales forecast/digest, task due dates, conversation cleaners, owner credential primitives.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors7.py > ../concierge-stack/core-rs/parity/vectors7.json
"""
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from fastapi import HTTPException

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import convo, owner_auth, sales, tasks  # noqa: E402

rng = random.Random(20261115)
UTC = timezone.utc

# ---- sales -------------------------------------------------------------------------------------------------
STATUS = ["new", "contacted", "booked", "won", "lost", "bogus", None, "NEW"]
VALUES = [None, 0, 100, 2500, 99999, 1, 5, 15, 25, 333]
forecast_cases = []
for _ in range(200):
    rows = [{"id": i, "status": rng.choice(STATUS), "value_cents": rng.choice(VALUES), "name": rng.choice(["A", "B", None])} for i in range(rng.randint(0, 14))]
    avg, per = rng.choice([None, 0, 10000, 5000, 333, 1]), rng.choice([1, 2, 50])
    forecast_cases.append({"rows": rows, "avg": avg, "per": per, "out": sales.forecast(rows, avg, per)})
money_cases = [{"cents": c, "out": sales._money(c)} for c in [0, 1, 49, 50, 51, 99, 100, 149, 150, 151, 249, 250, 350, 450, 99999, 100000, 123456789, 99999950, 99999949,
                                                              -50, -150, -250, -100000, -123456, 10**12 + 50, 10**15, 2**53 + 2]]
effective_cases = [{"lead": l, "avg": a, "out": sales.effective_value(l, a)} for l in ({}, {"value_cents": None}, {"value_cents": 0}, {"value_cents": 700}) for a in (None, 0, 500)]
digest_cases = []
for _ in range(40):
    s = {"days": rng.choice([7, 14]), "new_leads": rng.randint(0, 99), "contacted": rng.randint(0, 50), "booked": rng.randint(0, 50), "won": rng.randint(0, 30),
         "lost": rng.randint(0, 30), "won_value_cents": rng.choice([0, 50, 150, 1234567, 99999950]), "open_value_cents": rng.choice([0, 250, 100000, 7654321]),
         "weighted_value_cents": rng.choice([0, 349, 1500, 4567890]), "overdue_todos": rng.randint(0, 9), "leads_waiting": rng.choice([None, 0, 4])}
    name = rng.choice(["Trendi", "Café Ünï, Ltd"])
    subject, body = sales.digest_text({"name": name}, s)
    digest_cases.append({"name": name, "s": s, "subject": subject, "body": body})
due_cases = []
for d in range(7):
    for h in range(24):
        local = datetime(2026, 11, 9 + d, h, 30)
        due_cases.append({"wd": local.weekday(), "hour": h, "out": sales.digest_is_due(local)})

# ---- tasks ---------------------------------------------------------------------------------------------------
ZONES = [None, "", "UTC", "Pacific/Auckland", "America/New_York", "Europe/London", "Australia/Lord_Howe", "Asia/Kolkata"]
due_task_cases = []
for _ in range(500):
    tz = rng.choice(ZONES)
    tenant = {"timezone": tz, "sla_minutes": rng.choice([None, 0, 15, 90])}
    lead = {"score_label": rng.choice([None, "cold", "warm", "hot"])}
    now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randint(0, 365 * 86400))
    due_task_cases.append({"tz": tz, "sla": tenant["sla_minutes"], "hot": lead["score_label"] == "hot", "now": int(now.timestamp()),
                           "out": int(tasks.default_follow_up_due(tenant, lead, now).timestamp())})
# around 9am local on DST dates
for tz, day in [("Pacific/Auckland", "2026-09-27"), ("Pacific/Auckland", "2026-04-05"), ("America/New_York", "2026-03-08"), ("America/New_York", "2026-11-01"), ("Europe/London", "2026-03-29"), ("Europe/London", "2026-10-25")]:
    zi = ZoneInfo(tz)
    for minute in range(-180, 181, 20):
        local = datetime.fromisoformat(day + "T09:00:00").replace(tzinfo=zi) + timedelta(minutes=minute)
        now = local.astimezone(UTC)
        tenant = {"timezone": tz, "sla_minutes": None}
        due_task_cases.append({"tz": tz, "sla": None, "hot": False, "now": int(now.timestamp()), "out": int(tasks.default_follow_up_due(tenant, {}, now).timestamp())})
title_cases = []
for t in ["", "  ", None, "Call Ann", "  padded  ", "x" * 200, "x" * 201, "é" * 200, "é" * 201, "\t\n x 　"]:
    try:
        title_cases.append({"in": t, "out": {"ok": tasks.clean_title(t)}})
    except tasks.TaskError as e:
        title_cases.append({"in": t, "out": {"err": str(e)}})

# ---- convo ------------------------------------------------------------------------------------------------------
utm_cases = []
for _ in range(120):
    utm = {}
    for i in range(rng.randint(0, 14)):
        k = rng.choice(["utm_source", "utm_medium", f"utm_k{i}", "x_other", "UTM_upper", "utm_" + "z" * 50, "utm_dup"])
        utm[k] = rng.choice(["google", "é" * 250, "", 5, True, None, "a" * 201])
    utm_cases.append({"utm": utm, "out": convo.clean_utm(utm)})
utm_cases.append({"utm": {}, "out": convo.clean_utm(None)})
session_cases = []
for s in ["abcdefgh", "abc", "abcdefg", "a-b_c-d_e", "  spaced out id  ", "x" * 100, "é" * 20 + "valid-id", "日本語" * 5, "ab" * 33, "!!!!!!!!!!", "abcdefg!", "A" * 64 + "tail"]:
    try:
        session_cases.append({"in": s, "out": {"ok": convo.clean_session(s)}})
    except HTTPException as e:
        session_cases.append({"in": s, "out": {"err": [e.status_code, e.detail]}})

# ---- owner_auth ----------------------------------------------------------------------------------------------------
digest_auth = [{"in": t, "out": owner_auth.digest(t)} for t in ["", "tok", "é日本😀"]]
SALT = bytes(range(16))
hash_cases = []
for pw in ["short", "x" * 11, "123456789012", "pässwörd-ünï-12", "p" * 256, "p" * 257, "日本語のパスワード十二文字以上です"]:
    try:
        with mock.patch.object(owner_auth.secrets, "token_bytes", lambda n: SALT):
            hash_cases.append({"pw": pw, "salt_hex": SALT.hex(), "out": {"ok": owner_auth.password_hash(pw)}})
    except ValueError as e:
        hash_cases.append({"pw": pw, "salt_hex": SALT.hex(), "out": {"err": str(e)}})


def stored(pw, salt, rounds):
    return f"pbkdf2_sha256:{rounds}:{salt.hex()}:{hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, rounds).hex()}"


verify_cases = []
good = stored("correct horse battery", SALT, 1000)
for pw, st in [("correct horse battery", good), ("wrong", good), ("", good), ("correct horse battery", stored("correct horse battery", b"\x01" * 16, 1)),
               ("pässwörd-ünï", stored("pässwörd-ünï", SALT, 50)), ("x", "pbkdf2_sha1:1000:00:00"), ("x", "a:b:c"), ("x", "a:b:c:d:e"), ("x", ""),
               ("x", "pbkdf2_sha256:abc:00:00"), ("x", "pbkdf2_sha256: 5 :00:00"), ("x", "pbkdf2_sha256:+5:00:00"), ("x", "pbkdf2_sha256:0:00:00"), ("x", "pbkdf2_sha256:-5:00:00"),
               ("x", "pbkdf2_sha256:5:zz:00"), ("x", "pbkdf2_sha256:5:0:00"), ("x", "pbkdf2_sha256:5::00"), ("x", "pbkdf2_sha256:5:00:"), ("x", stored("x", b"", 7)),
               ("x", stored("x", SALT, 5)[:-2]), ("x", stored("x", SALT, 5).upper().replace("PBKDF2_SHA256", "pbkdf2_sha256"))]:
    verify_cases.append({"pw": pw, "stored": st, "out": owner_auth.verify_password(pw, st)})

email_cases = []
for e in ["a@b.co", "  A@B.CO ", "a@b", "@b.co", "a@@b.co", "a b@c.de", "a@b.c", "x" * 310 + "@y.zz", "x" * 320, "é@ü.de", "İ@x.co", "a@b.c\n", "a+tag@sub.example.co.uk", ""]:
    try:
        email_cases.append({"in": e, "out": {"ok": owner_auth.clean_email(e)}})
    except ValueError as ex:
        email_cases.append({"in": e, "out": {"err": str(ex)}})

print(json.dumps({"forecast": forecast_cases, "money": money_cases, "effective": effective_cases, "digest": digest_cases, "due": due_cases, "task_due": due_task_cases,
                  "titles": title_cases, "utm": utm_cases, "sessions": session_cases, "auth_digest": digest_auth, "hashes": hash_cases, "verify": verify_cases, "emails": email_cases},
                 ensure_ascii=False, indent=0, default=str))
