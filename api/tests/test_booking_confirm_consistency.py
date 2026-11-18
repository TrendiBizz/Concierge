"""Booking confirm: consent must not break the read-back match, and a racing duplicate confirm is a duplicate.

Review of PR #1 (2026-11-19): the read-back key included `consent`, so a confirmed=true call that
omitted consent_to_contact never matched and the visitor was asked to confirm forever. And when two
confirms for the same booking raced, the loser was told the time was "just taken" instead of
receiving the existing booking.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import booking
from tests.test_booking_creates_customer import TENANT, _AsyncCtx

START = datetime(2026, 11, 15, 21, 0, tzinfo=timezone.utc)
ARGS = {"name": "Sarah", "phone": "021 555 7788", "email": "", "start": "2026-11-16T10:00:00"}
CTX = {"channel": "chat", "conversation_id": "c1"}


def _patch(monkeypatch, pending, fetchrow, free):
    async def slots(tenant, day, conn=None):
        return free
    conn = SimpleNamespace(execute=AsyncMock(), fetchrow=AsyncMock(side_effect=fetchrow),
                           transaction=lambda: _AsyncCtx())
    pool = SimpleNamespace(acquire=lambda: _AsyncCtx(conn), fetchrow=AsyncMock(side_effect=fetchrow))
    monkeypatch.setattr(booking, "_slots_on", slots)
    monkeypatch.setattr(booking, "db", SimpleNamespace(pool=lambda: pool))
    monkeypatch.setattr(booking.casetimeline, "tenant_country_code", lambda t: "64")
    monkeypatch.setattr(booking.casetimeline, "reconcile", AsyncMock(return_value={"id": "case-1"}))
    monkeypatch.setattr(booking.convo, "get_pending_booking", AsyncMock(return_value=pending))
    monkeypatch.setattr(booking.convo, "set_pending_booking", AsyncMock())


def test_confirm_matches_even_if_consent_flag_differs(monkeypatch):
    key = {"start": START.isoformat(), "name": "sarah", "email": "", "phone": "+64215557788"}
    async def fetchrow(sql, *a):
        return None
    _patch(monkeypatch, key, fetchrow, [START])
    # First call asked with consent_to_contact; the confirm omits it.
    result = asyncio.run(booking.book(TENANT, dict(ARGS, confirmed=True), dict(CTX, dry_run=True)))
    assert result.get("ok") is True and not result.get("needs_confirmation"), result


def test_racing_duplicate_confirm_returns_the_existing_booking(monkeypatch):
    key = {"start": START.isoformat(), "name": "sarah", "email": "", "phone": "+64215557788"}
    existing = {"id": "appt-1", "status": "booked", "name": "Sarah", "email": "", "phone": "+64215557788",
                "starts_at": START, "calendar_state": "unconnected"}
    calls = {"n": 0}
    async def fetchrow(sql, *a):
        if "FROM appointments" in sql:
            calls["n"] += 1
            return None if calls["n"] == 1 else existing  # the winner commits between the two looks
        return None
    _patch(monkeypatch, key, fetchrow, [START])
    state = {"first": True}
    async def slots(tenant, day, conn=None):
        if conn is None:
            return [START]
        return []  # taken by the winner once we hold the lock
    monkeypatch.setattr(booking, "_slots_on", slots)
    result = asyncio.run(booking.book(TENANT, dict(ARGS, confirmed=True), CTX))
    assert result.get("duplicate") is True, result
