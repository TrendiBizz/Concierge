"""Enabling customer booking safely.

Booking looks like one switch (`tenants.native_booking`) but it needs usable BUSINESS HOURS to mean
anything. An owner can currently turn booking on with every day closed, or with a slot length longer
than the only opening window. The assistant then advertises a booking tool that can never return a
slot, and the customer is told "no free times" for every date they ask about. That is silent
breakage, not a missing feature: nothing errors, so nothing gets fixed.

These tests pin the properties that make enabling safe:
  - enabling with no usable opening hours is refused, and says why;
  - enabling with hours that cannot fit a single slot is refused;
  - a business with valid hours enables cleanly and immediately offers real slots;
  - disabling is always allowed, and needs no acknowledgement;
  - the readiness report distinguishes "switched on" from "actually able to take a booking".
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import booking, owner_onboarding

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "native_booking": False,
    "slot_minutes": 30,
    "min_notice_hours": 2,
    "max_days_ahead": 30,
    "business_hours": {
        "mon": [["09:00", "17:00"]], "tue": [["09:00", "17:00"]],
        "wed": [["09:00", "17:00"]], "thu": [["09:00", "17:00"]],
        "fri": [["09:00", "17:00"]], "sat": [], "sun": [],
    },
}


def _closed():
    return {d: [] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


# ---------------------------------------------------------------- hours analysis


def test_open_days_counts_only_days_with_a_window():
    assert owner_onboarding.open_day_count(TENANT["business_hours"]) == 5
    assert owner_onboarding.open_day_count(_closed()) == 0


def test_all_days_closed_enables_nothing():
    assert owner_onboarding.booking_hours_problem(_closed(), slot_minutes=30)


def test_a_window_shorter_than_one_slot_is_a_problem():
    """09:00-09:15 cannot fit a 30-minute slot, so booking would never offer anything."""
    hours = _closed()
    hours["mon"] = [["09:00", "09:15"]]
    assert owner_onboarding.booking_hours_problem(hours, slot_minutes=30)


def test_a_window_that_exactly_fits_one_slot_is_fine():
    """The boundary matters: 09:00-09:30 yields exactly one slot and must be accepted."""
    hours = _closed()
    hours["mon"] = [["09:00", "09:30"]]
    assert owner_onboarding.booking_hours_problem(hours, slot_minutes=30) == ""


def test_valid_hours_report_no_problem():
    assert owner_onboarding.booking_hours_problem(TENANT["business_hours"], slot_minutes=30) == ""


# ---------------------------------------------------------------- enable / disable


def test_enabling_without_usable_hours_is_refused(monkeypatch):
    """Refuse, rather than switch on a tool that can never book anything."""
    updated = []

    async def fake_update(slug, fields):
        updated.append(fields)
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)

    with pytest.raises(ValueError) as exc:
        asyncio.run(owner_onboarding.set_native_booking(
            {**TENANT, "business_hours": _closed()},
            enabled=True, acknowledgement=True,
        ))
    assert "hour" in str(exc.value).lower()
    assert not updated, "a refused enable must not have written the flag"


def test_enabling_without_acknowledgement_is_refused(monkeypatch):
    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    with pytest.raises(ValueError):
        asyncio.run(owner_onboarding.set_native_booking(TENANT, enabled=True, acknowledgement=False))


def test_enabling_with_good_hours_succeeds(monkeypatch):
    updated = {}

    async def fake_update(slug, fields):
        updated.update(fields)
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    result = asyncio.run(owner_onboarding.set_native_booking(
        TENANT, enabled=True, acknowledgement=True,
    ))
    assert updated["native_booking"] is True
    assert result["enabled"] is True
    assert result["ready"] is True


def test_disabling_needs_no_acknowledgement_and_always_works(monkeypatch):
    """Stopping bookings must never be harder than starting them."""
    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    result = asyncio.run(owner_onboarding.set_native_booking(
        {**TENANT, "native_booking": True, "business_hours": _closed()},
        enabled=False, acknowledgement=False,
    ))
    assert result["enabled"] is False


def test_disabling_is_possible_even_with_unusable_hours(monkeypatch):
    """An owner whose hours are broken must still be able to switch booking OFF."""
    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    result = asyncio.run(owner_onboarding.set_native_booking(
        {**TENANT, "native_booking": True, "business_hours": _closed()},
        enabled=False, acknowledgement=False,
    ))
    assert result["ready"] is False
    assert "hour" in result["reason"].lower(), "the reason should still explain the hours problem"


# ---------------------------------------------------------------- the real thing


def test_enabling_produces_real_slots(monkeypatch):
    """The point of enabling is that availability now returns times."""
    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    asyncio.run(owner_onboarding.set_native_booking(TENANT, enabled=True, acknowledgement=True))

    async def no_bookings(tenant_id, day, tz, conn=None):
        return []

    async def no_calendar_busy(tenant_id, start, end):
        return []

    monkeypatch.setattr(booking, "_booked", no_bookings)
    # A connected calendar is a separate integration; this test is about the hours producing slots.
    monkeypatch.setattr(booking.calendar_connection, "busy", no_calendar_busy)
    # A Wednesday, safely inside max_days_ahead and past min_notice.
    target = (datetime.now(booking.ZoneInfo("Pacific/Auckland")).date()
              + timedelta(days=2))
    while target.weekday() >= 5:  # skip the weekend so a window exists
        target += timedelta(days=1)
    result = asyncio.run(booking.availability(TENANT, target.isoformat()))
    assert result["ok"] is True
    assert result["slots"], "booking reported no slots for a valid open day"
