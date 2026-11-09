"""Batch-2 golden vectors: scoring, SLA alert text, next_allowed_send and day_slots from the live Python.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors2.py > ../concierge-stack/core-rs/parity/vectors2.json
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import booking, outbox, scoring, sla  # noqa: E402

rng = random.Random(20261110)
UTC = timezone.utc

# ---- scoring -------------------------------------------------------------------------------
MSGS = ["", "   ", "hi", "What is the price? How much to book an appointment today?", "PRICE price Prices PRICING",
        "Need a quote asap, urgent emergency, will buy and hire; start tomorrow, this week, availability?",
        "see https://spam.example or www.x.com now", "x" * 39, "x" * 40, "é" * 40, "how  much", "bookings are open", "ſtart", "Cost: $5",
        "I would like to ask about booking a very long appointment for my family next week please"]
NAMES = [None, "", " ", "A", "Al", " Al ", "日本"]
PAGES = [None, "", "https://x.test/pricing", "/Contact-us", "/about", "/CHECKOUT/step"]
CHANS = [None, "", "web", "sms", "voice", "email"]
BASE = lambda: scoring.DEFAULT_WEIGHTS.copy()  # noqa: E731
weight_sets = [None, {}, {"phone": 0}, {"intent_cap": 5, "intent_each": 20}, {"hot_at": 50, "warm_at": 10}, {"spam_link": -50, "booked": 50},
               {"intent_cap": 0}, {"intent_each": 0}, {"long_message": -3, "conversation": 7}]
score_cases = []
for _ in range(500):
    lead = {"message": rng.choice(MSGS + [None]), "phone": rng.choice([None, "", " ", "+6421"]), "email": rng.choice([None, "", "a@b.co"]),
            "name": rng.choice(NAMES), "consent_contact": rng.choice([True, False, None]), "channel": rng.choice(CHANS), "page_url": rng.choice(PAGES)}
    turns, booked, w = rng.randint(0, 6), rng.choice([True, False]), rng.choice(weight_sets)
    score_cases.append({"lead": lead, "turns": turns, "booked": booked, "weights": w, "out": scoring.assess(lead, turns, booked, w)})

override_cases = []
for raw in [{}, {"phone": 10}, {"phone": 51}, {"phone": -51}, {"phone": -50}, {"phone": 50}, {"phone": 1.5}, {"phone": 5.0}, {"phone": True}, {"phone": "5"},
            {"nope": 1}, {"intent_cap": 6}, {"intent_cap": -1}, {"hot_at": 0}, {"hot_at": 101}, {"warm_at": 80}, {"warm_at": 70}, {"hot_at": 30},
            {"hot_at": 30, "warm_at": 20}, [], "x", None, 5, {"zzz": True, "phone": 99}, {"phone": 99, "zzz": True}, {"phone": None}]:
    try:
        out = {"ok": scoring.validate_overrides(raw)}
    except ValueError as e:
        out = {"err": str(e)}
    override_cases.append({"raw": raw, "out": out})

weights_for_cases = [{"scoring": v, "out": scoring.weights_for({"scoring": v})} for v in
                     [None, {}, {"phone": 3}, '{"phone": 4}', "not json", "[]", {"hot_at": 90}, '{"warm_at":10,"hot_at":20}']]
describe = scoring.describe(None)
labels = [{"score": sc, "hot": h, "warm": wm, "out": scoring.label_for(sc, h, wm)} for sc in (0, 39, 40, 69, 70, 100) for h, wm in ((70, 40), (50, 10), (100, 99))]

# ---- sla -----------------------------------------------------------------------------------
sla_cases = []
for _ in range(60):
    lead = {"name": rng.choice([None, "", "Ann"]), "phone": rng.choice([None, "", "+6421"]), "email": rng.choice([None, "", "a@b.co"]),
            "channel": rng.choice([None, "web", "sms"]), "message": rng.choice([None, "", "Hello\nthere"]),
            "score_label": rng.choice(["hot", "warm", "ßtraße"]), "score": rng.randint(0, 100), "minutes_waiting": rng.randint(0, 5000)}
    tenant = {"name": rng.choice(["Trendi", "Café ünïcode"]), "sla_minutes": rng.randint(1, 120)}
    subject, body = sla._alert_text(tenant, lead)
    sla_cases.append({"tenant": tenant, "lead": lead, "subject": subject, "body": body})

# ---- next_allowed_send ----------------------------------------------------------------------
ZONES = ["Pacific/Auckland", "America/New_York", "Europe/London", "Australia/Lord_Howe", "America/St_Johns", "Asia/Kolkata", "UTC", "America/Sao_Paulo"]
nas_cases = []
for tzname in ZONES:
    for _ in range(120):
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randint(0, 365 * 86400))
        sh, eh = rng.choice([(8, 21), (8, 21), (0, 24), (9, 17), (6, 22)])
        out = outbox.next_allowed_send(ZoneInfo(tzname), when, sh, eh)
        nas_cases.append({"tz": tzname, "when": int(when.timestamp()), "start": sh, "end": eh, "out": int(out.timestamp())})
# hit DST transition instants directly
TRANS = {"Pacific/Auckland": ["2026-09-26T13:00:00", "2026-04-04T13:00:00"], "America/New_York": ["2026-03-08T07:00:00", "2026-11-01T06:00:00"],
         "Europe/London": ["2026-03-29T01:00:00", "2026-10-25T01:00:00"], "Australia/Lord_Howe": ["2026-10-03T15:30:00", "2026-04-04T15:00:00"]}
for tzname, stamps in TRANS.items():
    for st in stamps:
        base = datetime.fromisoformat(st).replace(tzinfo=UTC)
        for h in range(-30, 31, 3):
            when = base + timedelta(hours=h, minutes=rng.choice([0, 30, 59]))
            out = outbox.next_allowed_send(ZoneInfo(tzname), when)
            nas_cases.append({"tz": tzname, "when": int(when.timestamp()), "start": 8, "end": 21, "out": int(out.timestamp())})

# ---- day_slots -----------------------------------------------------------------------------
HOURS = [{"mon": [["09:00", "17:00"]]}, {"mon": [["09:00", "12:00"], ["13:00", "17:30"]]}, {"mon": [["00:00", "05:00"]]},
         {"mon": [["01:00", "04:00"]]}, {"mon": [["01:30", "03:30"]]}, {"mon": [["06:00", "22:00"]]}, {"mon": [["10:00", "10:20"]]}, {"mon": []}]
slot_cases = []
for tzname in ["Pacific/Auckland", "America/New_York", "Europe/London", "Australia/Lord_Howe", "America/St_Johns"]:
    days = [date(2026, 9, 27), date(2026, 9, 26), date(2026, 4, 5), date(2026, 3, 8), date(2026, 11, 1), date(2026, 3, 29), date(2026, 10, 25),
            date(2026, 10, 4), date(2026, 4, 5), date(2026, 11, 10), date(2026, 12, 25)] + [date(2026, 1, 1) + timedelta(days=rng.randint(0, 364)) for _ in range(10)]
    for day in days:
        for _ in range(4):
            hrs = rng.choice(HOURS)
            hours_all = {d: hrs.get("mon", []) for d in booking.DAYS}  # same hours every weekday so the DST dates are always open
            tenant = {"timezone": tzname, "slot_minutes": rng.choice([15, 20, 30, 45, 60, 90]), "min_notice_hours": rng.choice([0, 0, 2, 24]), "business_hours": hours_all}
            now = datetime.combine(day, datetime.min.time(), tzinfo=UTC) - timedelta(hours=rng.randint(-14, 96), minutes=rng.choice([0, 7, 30]))
            booked = []
            for _ in range(rng.randint(0, 3)):
                s = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(minutes=rng.randint(0, 1440))
                booked.append((s, s + timedelta(minutes=rng.choice([15, 30, 60, 120]))))
            out = booking.day_slots(tenant, day, now, booked)
            slot_cases.append({"tenant": tenant, "day": day.isoformat(), "now": int(now.timestamp()),
                               "booked": [[int(a.timestamp()), int(b.timestamp())] for a, b in booked], "out": [int(x.timestamp()) for x in out]})

print(json.dumps({"score": score_cases, "overrides": override_cases, "weights_for": weights_for_cases, "describe": describe, "labels": labels,
                  "sla": sla_cases, "nas": nas_cases, "slots": slot_cases}, ensure_ascii=False, indent=0, default=str))
