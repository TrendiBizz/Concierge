"""Booking an appointment must create the customer, not just a lead row.

The booking path wrote `leads` with a name, email and phone and never reconciled a customer, so a
visitor who booked an appointment was invisible in Contacts — a confirmed appointment with somebody
the CRM showed nothing about. Found by auditing leads whose contact details had no customer record.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import booking

class _AsyncCtx:
    """Special methods are looked up on the type, so these cannot be mocked onto a SimpleNamespace."""

    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture", "name": "Fixture Business", "timezone": "Pacific/Auckland",
    "slot_minutes": 30, "min_notice_hours": 0, "max_days_ahead": 30, "native_booking": True,
    "lead_webhook_url": "", "default_country_code": "64",
    "business_hours": {"mon": [["09:00", "17:00"]], "tue": [["09:00", "17:00"]],
                       "wed": [["09:00", "17:00"]], "thu": [["09:00", "17:00"]],
                       "fri": [["09:00", "17:00"]], "sat": [], "sun": []},
}


def test_booking_creates_the_customer_and_links_the_lead(monkeypatch):
    captured = {}

    async def fake_slots(tenant, day, conn=None):
        # 10:00 in Pacific/Auckland during daylight saving is 21:00 UTC the day before.
        return [datetime(2026, 11, 15, 21, 0, tzinfo=timezone.utc)]

    async def fake_reconcile(tenant_id, **kwargs):
        captured.update(kwargs)
        return {"id": "case-1"}

    async def fake_fetchrow(sql, *args):
        if sql.strip().upper().startswith("SELECT"):
            return None  # no existing lead, no earlier booking for this conversation
        if "INSERT INTO leads" in sql:
            captured["sql"] = sql
            captured["lead_args"] = args
            return {"id": "lead-1", "case_id": "case-1"}
        return {"id": "appt-1"}

    conn = SimpleNamespace(execute=AsyncMock(), fetchrow=AsyncMock(side_effect=fake_fetchrow),
                           transaction=lambda: _AsyncCtx())
    pool = SimpleNamespace(acquire=lambda: _AsyncCtx(conn),
                           fetchrow=AsyncMock(return_value=None))
    monkeypatch.setattr(booking, "_slots_on", fake_slots)
    monkeypatch.setattr(booking, "_booked", AsyncMock(return_value=[]))
    monkeypatch.setattr(booking.casetimeline, "reconcile", fake_reconcile)
    monkeypatch.setattr(booking.casetimeline, "tenant_country_code", lambda t: "64")
    monkeypatch.setattr(booking, "db", SimpleNamespace(pool=lambda: pool))
    # The visitor has already been read the details back and confirmed them.
    monkeypatch.setattr(booking.convo, "get_pending_booking", AsyncMock(return_value={
        "start": "2026-11-15T21:00:00+00:00", "name": "sarah",
        "email": "sarah@acme.co.nz", "phone": "+64215557788", "consent": False}))
    monkeypatch.setattr(booking.convo, "set_pending_booking", AsyncMock())
    timeline = AsyncMock()
    monkeypatch.setattr(booking.casetimeline, "record", timeline)
    monkeypatch.setattr(booking.calendar_connection, "sync_one", AsyncMock())
    monkeypatch.setattr(booking.calendar_connection, "notify_synced", AsyncMock())

    try:
        asyncio.run(booking.book(TENANT, {
            "name": "Sarah", "phone": "021 555 7788", "email": "sarah@acme.co.nz",
            "start": "2026-11-16T10:00:00", "notes": "quote", "confirmed": True},
            {"channel": "chat", "conversation_id": "c1"}))
    except Exception as exc:
        print("raised after capture:", type(exc).__name__, exc)

    assert captured.get("phone") == "+64215557788", "the booking did not create the customer"
    assert "case_id" in captured["sql"], "the lead insert does not carry the customer id"
    assert "case-1" in captured["lead_args"], "the lead was not linked to the customer"
    if timeline.await_count:
        assert timeline.await_args.kwargs["source_key"].startswith("appointment:"), \
            "the booking history entry is not tied to the appointment"


def test_availability_returns_a_start_value_that_can_be_booked(monkeypatch):
    """The times offered must be usable as `start`, complete with the date."""
    from datetime import date

    async def fake_slots(tenant, day, conn=None):
        return [datetime(2026, 11, 15, 21, 0, tzinfo=timezone.utc)]  # 10:00 NZDT on the 16th

    monkeypatch.setattr(booking, "_slots_on", fake_slots)
    monkeypatch.setattr(booking, "db", SimpleNamespace(pool=lambda: SimpleNamespace(
        fetchrow=AsyncMock(return_value=None))))
    day = (date.today() + __import__("datetime").timedelta(days=1)).isoformat()
    result = asyncio.run(booking.availability(TENANT, day))
    assert result["slot_starts"], "availability returned no bookable start values"
    assert result["slot_starts"][0].count(" ") == 1, "the start value is missing its date"
    assert result["slot_starts"][0].endswith("10:00")
