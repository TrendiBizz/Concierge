"""Batch-5 golden vectors: automation (run the real async functions with a fixed clock and a fake queue) and campaigns.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors5.py > ../concierge-stack/core-rs/parity/vectors5.json
"""
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ["UNSUBSCRIBE_SECRET"] = "parity-secret-not-real"
os.environ["PUBLIC_BASE_URL"] = "https://example.test/"
os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import automation, campaigns, outbox, sales, scoring, tasks, unsub  # noqa: E402

rng = random.Random(20261113)
UTC = timezone.utc
FIXED = datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC)


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


automation.datetime = FixedDT
cc_holder = {"cc": "1"}
automation.get_settings = lambda: SimpleNamespace(default_country_code=cc_holder["cc"])
enq, alerts, cancels = [], [], []


async def fake_enqueue(tenant_id, kind, channel, to_addr, body, subject="", send_at=None, dedupe_key=None, appointment_id=None, lead_id=None, campaign_id=None):
    enq.append({"kind": kind, "channel": channel, "to": to_addr, "subject": subject, "body": body, "send_at": int(send_at.timestamp()), "dedupe": dedupe_key})
    return True


async def fake_cancel(appointment_id):
    cancels.append(True)
    return 0


async def fake_alert(tenant, subject, body, dedupe):
    alerts.append({"subject": subject, "body": body, "dedupe": dedupe})


async def noop(*a, **k):
    return None


async def ident_apply(lead, booked=False, weights=None):
    return lead


outbox.enqueue = fake_enqueue
outbox.cancel_for_appointment = fake_cancel
automation._owner_alert = fake_alert
scoring.apply = ident_apply
tasks.create_follow_up = noop
sales.change_status = noop

ZONES = ["Pacific/Auckland", "America/New_York", "Europe/London", "Australia/Lord_Howe", "Asia/Kolkata", "UTC"]
NAMES = ["Ann", "Ann Lee", "  Ann   Lee ", "", "  ", "Zoë Ünï", "日本 語", "Bob\tSmith", None]
PHONES = ["", "+6421 123 4567", "021 123 4567", "(555) 123-4567", "5551234567", "12345", "+1234567"]
EMAILS = ["", "a@b.co", "bad", " a@b.co "]

appt_cases, status_cases = [], []
for _ in range(220):
    tz = rng.choice(ZONES)
    tenant = {"id": "t1", "name": rng.choice(["Trendi", "Café Ünï", "A & B, Ltd"]), "timezone": tz, "sms_enabled": rng.choice([True, False]),
              "review_url": rng.choice([None, "", "https://r.test/x"]), "lead_webhook_url": None}
    off = rng.choice([-5, 1, 1.5, 2, 2.5, 3, 12, 24, 25, 30, 100, 500])
    start = FIXED + timedelta(hours=off, minutes=rng.choice([0, 15, 30]))
    name = rng.choice(NAMES)
    appt = {"id": rng.choice(["a-1", "id-2"]), "starts_at": start, "ends_at": start + timedelta(minutes=30), "name": name or "", "phone": rng.choice(PHONES),
            "email": rng.choice(EMAILS), "notes": rng.choice(["", "bring ID", "x,y;z"]), "status": "booked", "consent_contact": rng.choice([True, False])}
    cc_holder["cc"] = rng.choice(["1", "64"])
    enq.clear(); alerts.clear()
    asyncio.run(automation.on_appointment_booked(tenant, appt, None))
    appt_cases.append({"tenant": {k: tenant[k] for k in ("name", "timezone", "sms_enabled", "review_url")}, "appt": {**appt, "starts_at": int(start.timestamp())}, "cc": cc_holder["cc"],
                       "alert": alerts[0], "enqueues": list(enq)})
    for status in ("cancelled", "no_show", "completed", "booked"):
        enq.clear(); cancels.clear()
        asyncio.run(automation.on_appointment_status(tenant, appt, status))
        status_cases.append({"tenant": {k: tenant[k] for k in ("name", "timezone", "sms_enabled", "review_url")}, "appt": {**appt, "starts_at": int(start.timestamp())},
                             "cc": cc_holder["cc"], "status": status, "cancel": bool(cancels), "enqueues": list(enq)})

lead_cases = []
for _ in range(150):
    created = FIXED
    lead = {"id": rng.choice(["l-1", "l-2"]), "name": rng.choice(NAMES), "email": rng.choice([None, "", "a@b.co"]), "phone": rng.choice([None, "", "+6421"]),
            "message": rng.choice([None, "", "Need a quote\nasap"]), "channel": rng.choice(["chat", "sms", "voice"]), "page_url": rng.choice([None, "", "https://x.test/p"]),
            "score": rng.choice([None, 0, 25, 85]), "score_label": rng.choice([None, "cold", "warm", "hot"]),
            "score_reasons": rng.choice([[], ["+25 Gave a phone number"], ["+25 a", "+10 b", "-25 c"]]), "utm": {}, "created_at": created}
    tenant = {"id": "t1", "name": rng.choice(["Trendi", "Café Ünï"]), "lead_webhook_url": None}
    alerts.clear()
    asyncio.run(automation.on_lead_created(tenant, lead))
    lead_cases.append({"business": tenant["name"], "lead": {k: v for k, v in lead.items() if k != "created_at"}, "alert": alerts[0]})

# ---- campaigns -------------------------------------------------------------------------------------------
TEMPLATES = ["Hi {first}", "{business} here", "{first} at {business}", "{{literal}}", "{first", "first}", "{", "}", "{}", "{0}", "{first!r}", "{first!x}", "{first:>10}",
             "{first:}", "{first.upper}", "{first[0]}", "{business!s}", "{ first }", "{FIRST}", "x" * 601, "x" * 600, "", "  ", "a{{b}}c{first}", "{{", "}}", "{first}}",
             "{{{first}}}", "{first!}", "{first!r", "{first:{business}}", "{first:", "{first!r:>3}", "é{first}日本", "{unknown}", "{first}{unknown}", "{a[}", "{a[b]c}",
             "line\n{first}\n", "{first!r:}", "{{}}{first}", "}{", "{first}{", "plain text", "100% {business}!", "{a{b}c}", "{[}]", "{first[}", "{!r}", "{:x}"]
LEAD_NAMES = ["", "Ann", "Ann Lee", " Ann Lee", "  ", "Zoë Ünï", "日本 語", "Bob\tSmith"]
template_cases = []
for t in TEMPLATES:
    try:
        campaigns.validate_template(t)
        verr = None
    except campaigns.CampaignError as e:
        verr = str(e)
    renders = []
    if verr is None:
        for n in LEAD_NAMES:
            try:
                renders.append({"name": n, "out": campaigns.render(t, {"name": n}, {"name": "Trendi; Bizz"})})
            except Exception as e:  # noqa: BLE001
                renders.append({"name": n, "err": type(e).__name__})
    template_cases.append({"t": t, "err": verr, "renders": renders})

footer_cases = []
for tenant in ({"id": "0a3e7155", "name": "Trendi", "notify_email": "o@b.co"}, {"id": "t", "name": "Café", "notify_email": ""}, {"id": "t", "name": "X", "notify_email": None}):
    for to in ("a@b.co", "日本@x.jp", "p+q@x.co"):
        footer_cases.append({"tenant": tenant, "to": to, "out": campaigns.email_footer(tenant, to)})

mask_cases = [{"in": c, "out": campaigns.mask(c)} for c in ["a@b.co", "@x.co", "alice@example.com", "+6421123456", "12345", "123456", "1234567", "", "ab", "日本語の連絡先", "x@"]]

START = FIXED
time_cases = []
for count in (0, 1, 2, 5, 11):
    for per in (-3, 0, 1, 3, 7, 13, 45, 60, 100, 999, 3600, 7200, 7):
        out = campaigns.send_times(START, count, per)
        time_cases.append({"count": count, "per": per, "out": [int((d - datetime(1970, 1, 1, tzinfo=UTC)) / timedelta(microseconds=1)) for d in out]})

RAWS = [{}, {"statuses": ["new"]}, {"statuses": []}, {"statuses": ["new", "bogus"]}, {"statuses": "new"}, {"statuses": [1]}, {"statuses": [["a"]]}, {"older_than_days": 0},
        {"older_than_days": 3650}, {"older_than_days": 3651}, {"older_than_days": -1}, {"older_than_days": "45"}, {"older_than_days": " 7 "}, {"older_than_days": "x"},
        {"older_than_days": 12.9}, {"older_than_days": None}, {"older_than_days": True}, {"older_than_days": [1]}, {"min_score": 100}, {"min_score": 101}, {"min_score": "50"},
        {"max_recipients": 0}, {"max_recipients": 1}, {"max_recipients": 100}, {"max_recipients": 9999}, {"max_recipients": None}, {"max_recipients": "20"}, {"max_recipients": -4},
        {"max_recipients": "abc"}, {"statuses": ["won", "lost", "booked", "contacted", "new"], "older_than_days": 1, "min_score": 5, "max_recipients": 3}, {"max_recipients": 2.5}]
filter_cases = []
for m in (500, 50):
    campaigns.get_settings = lambda m=m: SimpleNamespace(campaign_max_recipients=m, email_configured=True)
    for raw in RAWS:
        try:
            out = {"ok": campaigns.clean_filters(raw)}
        except campaigns.CampaignError as e:
            out = {"err": "CampaignError", "msg": str(e)}
        except ValueError:
            out = {"err": "ValueError"}
        except TypeError:
            out = {"err": "TypeError"}
        filter_cases.append({"max": m, "raw": raw, "out": out})

ready_cases = []
for enabled in (True, False):
    for ch in ("sms", "email"):
        for sms_on in (True, False):
            for sender in (True, False):
                for email_cfg in (True, False):
                    for unsub_ok in (True, False):
                        campaigns.get_settings = lambda e=email_cfg: SimpleNamespace(campaign_max_recipients=500, email_configured=e)
                        campaigns.sms.sender_ready = lambda t, s=sender: s
                        campaigns.unsub.available = lambda u=unsub_ok: u
                        out = campaigns.readiness({"campaigns_enabled": enabled, "sms_enabled": sms_on}, ch)
                        ready_cases.append({"enabled": enabled, "ch": ch, "sms": sms_on, "sender": sender, "email_cfg": email_cfg, "unsub": unsub_ok, "out": out})

print(json.dumps({"appt": appt_cases, "status": status_cases, "lead": lead_cases, "templates": template_cases, "footers": footer_cases, "mask": mask_cases,
                  "times": time_cases, "filters": filter_cases, "ready": ready_cases, "now": int(FIXED.timestamp())}, ensure_ascii=False, indent=0, default=str))
