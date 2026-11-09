"""Batch-3 golden vectors: quotation maths, fmt_local, local-time resolution, booking wording.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors3.py > ../concierge-stack/core-rs/parity/vectors3.json
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import automation, booking, quotations  # noqa: E402

rng = random.Random(20261111)
UTC = timezone.utc
ZONES = ["Pacific/Auckland", "America/New_York", "Europe/London", "Australia/Lord_Howe", "America/St_Johns", "Asia/Kolkata", "UTC", "America/Sao_Paulo", "Asia/Kathmandu"]

QTY = ["1", "2", "1.5", "1.500", "1.5000", "0.001", "0.0005", "0.0001", "0.333", "2.675", "100000", "100000.0", "100000.001", "100001", "0", "-1", ".5", "5.", "+2",
       " 3 ", "007", "007.50", "1e2", "1_0", "abc", "", "1.2.3", "99999.999", "12.345", "0.500"]
DESC = ["Labour", "  padded  ", "", "   ", "tab\there", "x" * 300, "x" * 301, "é日本語", "new\nline"]
PRICE = [0, 1, 99, 100, 1999, 12345, 100_000_000, 100_000_001, -1]
TAX = [0, 1, 1500, 1250, 10000, 10001, -1, 333]
quote_cases = []
for _ in range(700):
    pick = lambda good, allv: rng.choice(good if rng.random() < 0.93 else allv)  # noqa: E731
    lines = [{"description": pick(DESC[:2] + DESC[6:7], DESC), "quantity": pick(QTY[:13] + QTY[14:15] + QTY[15:16] * 0 + QTY[16:23] + QTY[27:30], QTY),
              "unit_price_cents": pick(PRICE[:7], PRICE)} for _ in range(rng.randint(1, 4))]
    tax = pick(TAX[:5] + TAX[7:], TAX)
    draft = {"lead_id": "0a3e7155-2f19-4527-bee1-f2dec7b676c7", "title": "T", "currency": "NZD", "tax_basis_points": tax, "lines": lines}
    try:
        model = quotations.QuoteDraft(**draft)
        out_lines, subtotal, taxc, total = quotations.calculate(model)
        out = {"ok": {"lines": out_lines, "subtotal": subtotal, "tax": taxc, "total": total}}
    except (ValidationError, HTTPException) as e:
        out = {"err": True, "cap": isinstance(e, HTTPException)}
    quote_cases.append({"lines": lines, "tax": tax, "out": out})
# total-cap boundary
for qty, price in (("100000", 100_000_000), ("100000", 99_999_999), ("99999.999", 100_000_000)):
    for n in (1, 2, 11, 12):
        lines = [{"description": "big", "quantity": qty, "unit_price_cents": price} for _ in range(n)]
        draft = {"lead_id": "0a3e7155-2f19-4527-bee1-f2dec7b676c7", "title": "T", "currency": "NZD", "tax_basis_points": 10000, "lines": lines}
        try:
            m = quotations.QuoteDraft(**draft)
            ol, st, tx, to = quotations.calculate(m)
            out = {"ok": {"lines": ol, "subtotal": st, "tax": tx, "total": to}}
        except (ValidationError, HTTPException) as e:
            out = {"err": True, "cap": isinstance(e, HTTPException)}
        quote_cases.append({"lines": lines, "tax": 10000, "out": out})

fmt_cases = []
for tz in ZONES:
    for _ in range(80):
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randint(0, 365 * 86400))
        fmt_cases.append({"tz": tz, "when": int(when.timestamp()), "out": automation.fmt_local({"timezone": tz}, when)})
for tz, stamp in [("Pacific/Auckland", "2026-11-10T21:00:00"), ("America/New_York", "2026-03-08T07:00:00"), ("Europe/London", "2026-10-25T00:30:00")]:
    base = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
    for h in range(-4, 5):
        when = base + timedelta(hours=h)
        fmt_cases.append({"tz": tz, "when": int(when.timestamp()), "out": automation.fmt_local({"timezone": tz}, when)})

resolve_cases = []
GAPS = {"Pacific/Auckland": ["2026-09-27T02:30", "2026-04-05T02:30"], "America/New_York": ["2026-03-08T02:30", "2026-11-01T01:30"],
        "Europe/London": ["2026-03-29T01:30", "2026-10-25T01:30"], "Australia/Lord_Howe": ["2026-10-04T02:15", "2026-04-05T01:45"]}
for tz, stamps in GAPS.items():
    for st in stamps:
        base = datetime.fromisoformat(st)
        for m in range(-120, 121, 15):
            local = base + timedelta(minutes=m)
            tzi = ZoneInfo(tz)
            utc = local.replace(tzinfo=tzi).astimezone(UTC)
            exists = utc.astimezone(tzi).replace(tzinfo=None) == local
            resolve_cases.append({"tz": tz, "local": local.isoformat(), "out": int(utc.timestamp()) if exists else None})

wording = []
for tz in ZONES[:5]:
    for _ in range(25):
        when = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randint(0, 365 * 86400))
        cal = rng.choice([None, "synced", "pending", "unconnected"])
        appt = {"id": "abc-123", "starts_at": when, "calendar_state": cal, "invitation_state": rng.choice([None, "sent", "pending"])}
        dup = rng.choice([True, False])
        name, phone, email = rng.choice(["Ann", "Zoë"]), rng.choice(["", "+6421"]), rng.choice(["", "a@b.co"])
        tenant = {"timezone": tz}
        res = booking.booking_result(tenant, {k: v for k, v in appt.items() if v is not None}, duplicate=dup)
        rb = f"{name}, {automation.fmt_local(tenant, when)}. We'll confirm with you at {phone or email}."
        wording.append({"tz": tz, "when": int(when.timestamp()), "cal": cal, "inv": appt["invitation_state"], "dup": dup, "name": name,
                        "phone": phone, "email": email, "result": res, "read_back": rb})

transitions = {k: ["draft"] for k in ()}
print(json.dumps({"quote": quote_cases, "fmt": fmt_cases, "resolve": resolve_cases, "wording": wording}, ensure_ascii=False, indent=0, default=str))
