"""Real native booking/calendar flow on disposable PostgreSQL; no external delivery."""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.update(DATABASE_URL="postgresql://postgres:test@127.0.0.1:55432/postgres",
                  OUTBOX_ENABLED="false", ADMIN_TOKEN="isolated-booking-test")
from fastapi.testclient import TestClient
from app import booking, convo, db, tenants
from app.main import app

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)

with TestClient(app) as client:
    async def exercise():
        suffix = secrets.token_hex(5)
        businesses = []
        for label in ("a", "b"):
            t = await tenants.create("Booking QA " + label + suffix, None)
            t = await tenants.update(t["slug"], {
                "native_booking": True, "timezone": "Pacific/Auckland", "min_notice_hours": 0,
                "max_days_ahead": 30, "slot_minutes": 30,
                "business_hours": {d: [["09:00", "12:00"]] for d in booking.DAYS},
            })
            businesses.append(t)
        a, b = businesses
        day = (datetime.now(ZoneInfo(a["timezone"])) + timedelta(days=2)).date()
        free = await booking.availability(a, day.isoformat())
        assert free["ok"] and free["slots"], free
        start = f"{day} {free['slots'][0]}"
        args = {"start": start, "name": "Synthetic Booker", "email": "booker@example.invalid"}
        contexts = []
        for label in ("first", "second"):
            cid = await convo.get_or_create(a, label + suffix, "chat", None, None)
            ctx = {"conversation_id": cid, "channel": "chat"}
            # Even a forged first-call confirmed=true must request read-back.
            pending = await booking.book(a, {**args, "confirmed": True}, ctx)
            assert pending.get("needs_confirmation") and not pending["ok"], pending
            contexts.append(ctx)
        assert await db.pool().fetchval("SELECT count(*) FROM appointments WHERE tenant_id=$1", a["id"]) == 0
        results = await asyncio.gather(*(booking.book(a, {**args, "confirmed": True}, c) for c in contexts))
        assert sum(r["ok"] for r in results) == 1, results
        assert free["slots"][0] not in (await booking.availability(a, day.isoformat()))["slots"]
        assert free["slots"][0] in (await booking.availability(b, day.isoformat()))["slots"]
        assert await db.pool().fetchval("SELECT count(*) FROM appointments WHERE tenant_id=$1", a["id"]) == 1
        assert await db.pool().fetchval("SELECT count(*) FROM appointments WHERE tenant_id=$1", b["id"]) == 0
        lead = await db.pool().fetchrow("SELECT status FROM leads WHERE tenant_id=$1", a["id"])
        assert lead["status"] == "booked"
        assert not (await booking.book(a, {**args, "start": f"{day} 22:00"}, contexts[0]))["ok"]
        assert not (await booking.availability(a, (day + timedelta(days=40)).isoformat()))["ok"]
        return a, b
    a, b = client.portal.call(exercise)
    path = "/api/v1/calendar/" + a["calendar_token"] + ".ics"
    feed = client.get(path)
    assert feed.status_code == 200 and "Synthetic Booker" in feed.text
    other = client.get("/api/v1/calendar/" + b["calendar_token"] + ".ics")
    assert other.status_code == 200 and "Synthetic Booker" not in other.text
    assert client.get("/api/v1/calendar/invalid-token.ics").status_code == 404
print("BOOKING_PASS: availability, read-back, concurrent conflict, tenant isolation, booked lead, limits, calendar feeds")
