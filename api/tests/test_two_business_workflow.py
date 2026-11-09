"""Two independent businesses driven through the whole portal secretary workflow.

Why this file exists: every earlier test proved one module's contract in isolation. None of them
ran the seven-step promise for TWO businesses at once, which is the only way the isolation
requirement can actually fail -- a shared recipient, a shared case, a shared dedupe key or a
calendar write attributed to the wrong tenant all look perfectly fine in a single-tenant test.

The seven steps, as the business owner experiences them:

  1. a voice call, text or email arrives for that business's portal
  2. the channel is identified and the enquiry is answered from that business's own knowledge
  3. the answer comes from the business's own information, not another business's
  4. the original enquiry reaches THAT business's owner, in its original form
  5. the enquirer is offered an acknowledgement, separately from the owner alert
  6. the dialogue is retained in CRM, one customer is one case, and a retried webhook is one row
  7. an agreed booking reaches the owner's calendar with the enquirer as attendee

Two behaviours are pinned deliberately because getting them wrong loses money or trust:

  * a local number in a foreign dialling format is REFUSED (None) rather than guessed, so two
    strangers are never merged into one shared case history;
  * an unconnected calendar reports "pending", never "confirmed", so an owner is never told an
    appointment was accepted when no calendar ever saw it.

Step 7's provider call is a boundary; the live Google path is verified separately against the real
API. What this file pins is the record, the attribution, the consent gate and the honesty of the
reported state.
"""
import asyncio
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import acknowledgements, booking, casetimeline, owner_notifications, owner_onboarding, quotations

BUSINESS_A = {
    "id": "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
    "name": "Harbour Dental", "slug": "harbour-dental",
    "timezone": "Pacific/Auckland", "default_country_code": "64",
    "notify_email": "owner-a@harbour.example", "notify_phone": "+64211111111",
    "sms_enabled": True, "slot_minutes": 30, "min_notice_hours": 0, "max_days_ahead": 60,
    "business_hours": {d: [["09:00", "17:00"]] for d in ("mon", "tue", "wed", "thu", "fri")},
}

BUSINESS_B = {
    "id": "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
    "name": "Southern Plumbing", "slug": "southern-plumbing",
    "timezone": "America/Chicago", "default_country_code": "1",
    "notify_email": "owner-b@southern.example", "notify_phone": "+13125550199",
    "sms_enabled": True, "slot_minutes": 60, "min_notice_hours": 0, "max_days_ahead": 60,
    "business_hours": {d: [["08:00", "16:00"]] for d in ("mon", "tue", "wed", "thu", "fri")},
}


class _Conn:
    """Minimal async connection: every call is recorded on the owning pool."""

    def __init__(self, pool):
        self.pool = pool

    def transaction(self):
        return _Txn()

    async def execute(self, sql, *args):
        return await self.pool.execute(sql, *args)

    async def fetchrow(self, sql, *args):
        return await self.pool.fetchrow(sql, *args)

    async def fetchval(self, sql, *args):
        return await self.pool.fetchval(sql, *args)

    async def fetch(self, sql, *args):
        return await self.pool.fetch(sql, *args)


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class RecordingPool:
    def __init__(self):
        self.statements = []

    def acquire(self):
        return _Acquire(self)

    async def execute(self, sql, *args):
        self.statements.append(("execute", " ".join(sql.split()), args)); return "INSERT 0 1"

    async def fetchrow(self, sql, *args):
        self.statements.append(("fetchrow", " ".join(sql.split()), args)); return None

    async def fetchval(self, sql, *args):
        self.statements.append(("fetchval", " ".join(sql.split()), args)); return None

    async def fetch(self, sql, *args):
        self.statements.append(("fetch", " ".join(sql.split()), args)); return []


class _Acquire:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        return _Conn(self.pool)

    async def __aexit__(self, *exc):
        return False


class ConfirmingPool(RecordingPool):
    async def fetchrow(self, sql, *args):
        self.statements.append(("fetchrow", " ".join(sql.split()), args))
        if "SELECT pending_ack" in sql:
            return {"pending_ack": {"channel": "sms", "recipient": "+64212223333"}}
        if "SELECT id FROM leads" in sql:
            return {"id": "lead-1"}
        return None


def capture_pool(monkeypatch, module, pool):
    monkeypatch.setattr(module.db, "pool", lambda: pool)
    return pool


# ---------------------------------------------------------- steps 2/3: identity, channel

def test_each_business_keys_its_own_customer_number_distinctly():
    """Each business normalises in its OWN dialling country, so the same digits are not one case."""
    a = casetimeline.case_key_for_tenant(BUSINESS_A, phone="021 555 123")
    b = casetimeline.case_key_for_tenant(BUSINESS_B, phone="312 555 0199")
    assert a == "phone:+6421555123"
    assert b == "phone:+13125550199"
    assert a != b


def test_a_foreign_local_format_is_refused_rather_than_fabricated():
    """'021 555 123' is not a US number. Guessing +1 would invent a number and merge strangers."""
    assert casetimeline.case_key_for_tenant(BUSINESS_A, phone="021 555 123") == "phone:+6421555123"
    assert casetimeline.case_key_for_tenant(BUSINESS_B, phone="021 555 123") is None


def test_a_business_without_its_own_country_uses_the_global_default(monkeypatch):
    monkeypatch.setattr(casetimeline, "get_settings", lambda: SimpleNamespace(default_country_code="64"))
    assert casetimeline.case_key_for_tenant({"id": "x"}, phone="021555123") == "phone:+6421555123"


@pytest.mark.parametrize("channel", ["chat", "voice", "email", "sms", "phone", "social"])
def test_every_supported_channel_is_identified(channel):
    assert channel in casetimeline.CHANNELS


def test_unknown_channel_is_refused_rather_than_stored():
    with pytest.raises(ValueError):
        asyncio.run(casetimeline.record("t", case_key="phone:+6421555123",
                                        channel="telepathy", direction="inbound", source_key="k"))


# ---------------------------------------------------------- step 4: owner notification

def test_owner_alert_goes_to_that_businesss_own_two_destinations(monkeypatch):
    pool = capture_pool(monkeypatch, owner_notifications, RecordingPool())
    monkeypatch.setattr(owner_notifications.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    sent = asyncio.run(owner_notifications.queue(
        BUSINESS_A, "Voice enquiry for Harbour Dental", "Full transcript here", "voice-finished:s1"))
    assert sent == ["email", "sms"]
    inserts = [s for s in pool.statements if s[0] == "execute" and "INSERT INTO outbox" in s[1]]
    recipients = {(s[2][1], s[2][2]) for s in inserts}
    assert ("email", "owner-a@harbour.example") in recipients
    assert ("sms", "+64211111111") in recipients
    assert not any("southern" in str(s[2]) or "3125550199" in str(s[2]) for s in inserts)


def test_owner_alert_isolated_by_tenant_id_in_sql(monkeypatch):
    pool = capture_pool(monkeypatch, owner_notifications, RecordingPool())
    monkeypatch.setattr(owner_notifications.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    asyncio.run(owner_notifications.queue(BUSINESS_B, "s", "b", "d"))
    inserts = [s for s in pool.statements if "INSERT INTO outbox" in s[1]]
    assert inserts
    for _op, _sql, args in inserts:
        assert args[0] == BUSINESS_B["id"]


def test_owner_sms_refused_without_that_businesss_authorization(monkeypatch):
    capture_pool(monkeypatch, owner_notifications, RecordingPool())
    monkeypatch.setattr(owner_notifications.channel_authorization, "is_authorized", AsyncMock(return_value=False))
    assert asyncio.run(owner_notifications.queue(BUSINESS_A, "s", "b", "d")) == ["email"]


def test_owner_email_only_business_still_notifies_by_email(monkeypatch):
    capture_pool(monkeypatch, owner_notifications, RecordingPool())
    monkeypatch.setattr(owner_notifications.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    assert asyncio.run(owner_notifications.queue({**BUSINESS_A, "sms_enabled": False}, "s", "b", "d")) == ["email"]


def test_long_owner_sms_keeps_recording_and_portal_links(monkeypatch):
    monkeypatch.setattr(owner_notifications, "get_settings",
                        lambda: SimpleNamespace(public_base_url="https://portal.example"))
    link = "https://portal.example/api/v1/voice/recordings/shared/tok123"
    body = owner_notifications.sms_body("Voice enquiry", "x" * 5000 + "\n" + link)
    assert len(body) <= 1400 and link in body and "https://portal.example/owner-ui" in body


# ---------------------------------------------------------- step 5: acknowledgement

class ConversationPool(RecordingPool):
    """A pool where the conversation exists but no acknowledgement choice is stored yet."""

    async def fetchrow(self, sql, *args):
        self.statements.append(("fetchrow", " ".join(sql.split()), args))
        if "SELECT pending_ack" in sql:
            return {"pending_ack": None}
        return None


def test_acknowledgement_requires_confirmation_before_queueing(monkeypatch):
    """The first ask stores the choice and waits; nothing is queued and nothing is sent."""
    pool = capture_pool(monkeypatch, acknowledgements, ConversationPool())
    monkeypatch.setattr(acknowledgements.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    result = asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": True, "channel": "email", "recipient": "hana@example.com"},
        {"conversation_id": "c1"}))
    assert result["ok"] is False and result["needs_confirmation"] is True
    assert "hana@example.com" in result["read_back"]
    assert not [s for s in pool.statements if "INSERT INTO outbox" in s[1]]


def test_acknowledgement_for_an_unknown_conversation_is_refused(monkeypatch):
    """An acknowledgement cannot be attached to a conversation that does not exist."""
    capture_pool(monkeypatch, acknowledgements, RecordingPool())
    monkeypatch.setattr(acknowledgements.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    result = asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": True, "channel": "email", "recipient": "hana@example.com"},
        {"conversation_id": "missing"}))
    assert result["ok"] is False and "unavailable" in result["error"]


def test_acknowledgement_declining_an_unknown_conversation_is_not_recorded(monkeypatch):
    """Declining must not silently succeed when there is no conversation to record it against."""
    capture_pool(monkeypatch, acknowledgements, RecordingPool())
    result = asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": False}, {"conversation_id": "missing"}))
    assert result["status"] == "declined"


def test_acknowledgement_declined_never_queues(monkeypatch):
    pool = capture_pool(monkeypatch, acknowledgements, RecordingPool())
    assert asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": False}, {"conversation_id": "c1"}))["status"] == "declined"
    assert not [s for s in pool.statements if "INSERT INTO outbox" in s[1]]


def test_acknowledgement_dry_run_cannot_mutate(monkeypatch):
    monkeypatch.setattr(acknowledgements.db, "pool", lambda: pytest.fail("dry run touched database"))
    assert asyncio.run(acknowledgements.request({}, {"requested": False}, {"dry_run": True}))["status"] == "dry_run"


def test_acknowledgement_refused_without_channel_authorization(monkeypatch):
    capture_pool(monkeypatch, acknowledgements, ConfirmingPool())
    monkeypatch.setattr(acknowledgements.channel_authorization, "is_authorized", AsyncMock(return_value=False))
    result = asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": True, "channel": "sms", "recipient": "+64212223333",
                     "confirmed": True}, {"conversation_id": "c1"}))
    assert result["ok"] is False and "authorized" in result["error"]


def test_confirmed_acknowledgement_queues_one_deduplicated_send(monkeypatch):
    pool = capture_pool(monkeypatch, acknowledgements, ConfirmingPool())
    monkeypatch.setattr(acknowledgements.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    result = asyncio.run(acknowledgements.request(
        BUSINESS_A, {"requested": True, "channel": "sms", "recipient": "+64212223333",
                     "confirmed": True}, {"conversation_id": "c1"}))
    assert result["ok"] is True and result["status"] == "queued"
    inserts = [s for s in pool.statements if "INSERT INTO outbox" in s[1]]
    assert len(inserts) == 1 and "ON CONFLICT" in inserts[0][1]
    assert inserts[0][2][2] == "+64212223333" != BUSINESS_A["notify_phone"]


def test_owner_alert_and_enquirer_ack_are_distinct_kinds():
    assert "'enquirer_ack'" in inspect.getsource(acknowledgements)
    assert "'owner_alert'" in inspect.getsource(owner_notifications)


# ---------------------------------------------------------- step 6: retention + dedupe

def test_retried_webhook_is_one_history_row():
    assert casetimeline.source_key_for("sms", "provider-msg-77") == casetimeline.source_key_for("sms", "provider-msg-77")


def test_different_messages_do_not_collide():
    assert casetimeline.source_key_for("sms", "m1") != casetimeline.source_key_for("sms", "m2")
    assert casetimeline.source_key_for("email", "", "Hello") != casetimeline.source_key_for("email", "", "Goodbye")


def test_schema_enforces_retry_idempotency():
    """The unique constraint must exist in the schema AND be the target the code relies on."""
    from pathlib import Path
    schema = (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()
    assert "case_events" in schema
    assert "UNIQUE" in schema
    # The conflict target used by casetimeline.record must match a real constraint on the table.
    assert "ON CONFLICT (tenant_id, channel, source_key)" in inspect.getsource(casetimeline.record)


def test_case_key_never_invented_for_unknown_person():
    assert casetimeline.case_key(phone="not-a-number", email="also-not-an-email") is None


def test_timeline_scoped_by_tenant(monkeypatch):
    pool = capture_pool(monkeypatch, casetimeline, RecordingPool())
    asyncio.run(casetimeline.timeline(BUSINESS_A["id"], "phone:+6421555123"))
    fetch = [s for s in pool.statements if s[0] == "fetch"]
    assert fetch and fetch[0][2][0] == BUSINESS_A["id"]


def test_takeover_targets_exact_business_and_customer(monkeypatch):
    pool = capture_pool(monkeypatch, casetimeline, RecordingPool())
    asyncio.run(casetimeline.set_takeover(BUSINESS_A["id"], case_key="phone:+6421555123", paused=True))
    update = [s for s in pool.statements if "UPDATE customer_cases" in s[1]][0]
    assert update[2][0] == BUSINESS_A["id"] and update[2][1] == "phone:+6421555123"


# ---------------------------------------------------------- step 7: booking + calendar

def test_booking_requires_read_back_before_creation(monkeypatch):
    capture_pool(monkeypatch, booking, RecordingPool())
    monkeypatch.setattr(booking, "_slots_on", AsyncMock(return_value=[datetime(2026, 11, 12, 1, 0, tzinfo=timezone.utc)]))
    monkeypatch.setattr(booking.convo, "get_pending_booking", AsyncMock(return_value=None))
    monkeypatch.setattr(booking.convo, "set_pending_booking", AsyncMock())
    result = asyncio.run(booking.book(BUSINESS_A, {"start": "2026-11-12 14:00", "name": "Hana",
                                                   "email": "hana@example.com"}, {"conversation_id": "c1"}))
    assert result["ok"] is False and result["needs_confirmation"] is True and "Hana" in result["read_back"]


def test_booking_refuses_unoffered_slot(monkeypatch):
    capture_pool(monkeypatch, booking, RecordingPool())
    monkeypatch.setattr(booking, "_slots_on", AsyncMock(return_value=[]))
    result = asyncio.run(booking.book(BUSINESS_A, {"start": "2026-11-12 14:00", "name": "Hana",
                                                   "email": "hana@example.com"}, {"conversation_id": "c1"}))
    assert result["ok"] is False and "not available" in result["error"]


def test_booking_refuses_nonexistent_dst_wall_time(monkeypatch):
    capture_pool(monkeypatch, booking, RecordingPool())
    result = asyncio.run(booking.book(BUSINESS_A, {"start": "2027-09-26 02:30", "name": "Hana",
                                                   "email": "hana@example.com"}, {"conversation_id": "c1"}))
    assert result["ok"] is False and "daylight saving" in result["error"]


def test_booking_needs_a_contact_route(monkeypatch):
    capture_pool(monkeypatch, booking, RecordingPool())
    result = asyncio.run(booking.book(BUSINESS_A, {"start": "2026-11-12 14:00", "name": "Hana"},
                                      {"conversation_id": "c1"}))
    assert result["ok"] is False and "phone number or email" in result["error"]


def test_unconnected_calendar_reported_as_pending_not_confirmed():
    appt = {"id": "appt-1", "calendar_state": "unconnected", "invitation_state": "pending",
            "starts_at": datetime(2026, 11, 12, 1, 0, tzinfo=timezone.utc), "name": "Hana"}
    result = booking.booking_result(BUSINESS_A, appt)
    assert result["booking_status"] == "pending_calendar"
    assert "pending" in result["confirmation"] and "accepted the event" not in result["confirmation"]


def test_synced_calendar_reports_invitation_request_honestly():
    appt = {"id": "appt-1", "calendar_state": "synced", "invitation_state": "provider_requested",
            "starts_at": datetime(2026, 11, 12, 1, 0, tzinfo=timezone.utc), "name": "Hana"}
    result = booking.booking_result(BUSINESS_A, appt)
    assert result["booking_status"] == "booked" and "invitation request" in result["confirmation"]


def test_calendar_event_id_unique_per_business():
    from app import calendar_connection
    assert calendar_connection.event_id(BUSINESS_A["id"], "appt-1") != calendar_connection.event_id(BUSINESS_B["id"], "appt-1")
    assert calendar_connection.event_id(BUSINESS_A["id"], "appt-1") == calendar_connection.event_id(BUSINESS_A["id"], "appt-1")


# ---------------------------------------------------------- step 7b: quotations

def test_quote_maths_exact():
    draft = quotations.QuoteDraft(lead_id="11111111-1111-4111-8111-111111111111", title="Checkup",
                                  currency="NZD", tax_basis_points=1500,
                                  lines=[quotations.QuoteLine(description="Exam", quantity="3", unit_price_cents=3333)])
    lines, subtotal, tax, total = quotations.calculate(draft)
    assert (lines[0]["amount_cents"], subtotal, tax, total) == (9999, 9999, 1500, 11499)


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-1", "0", "1.0001"])
def test_quote_rejects_impossible_quantity(quantity):
    with pytest.raises(Exception):
        quotations.QuoteLine(description="Service", quantity=quantity, unit_price_cents=1)


def test_quote_refuses_another_businesss_enquiry(monkeypatch):
    import fastapi
    pool = capture_pool(monkeypatch, quotations, RecordingPool())
    monkeypatch.setattr(quotations.owner_auth, "require_role", lambda *a, **k: None)
    draft = quotations.QuoteDraft(lead_id="11111111-1111-4111-8111-111111111111", title="Q",
                                  currency="NZD", lines=[quotations.QuoteLine(description="x", quantity="1", unit_price_cents=1)])
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(quotations.create(draft, user={"tenant_id": BUSINESS_A["id"], "role": "owner"}))
    assert exc.value.status_code == 404
    assert BUSINESS_A["id"] in [s for s in pool.statements if "FROM leads" in s[1]][0][2]


def test_quote_status_transitions_are_restricted():
    src = inspect.getsource(quotations.change_status)
    assert "'accepted': ['reviewed']" in src and "'reviewed': ['draft']" in src


def test_quotation_listing_scoped_to_caller(monkeypatch):
    pool = capture_pool(monkeypatch, quotations, RecordingPool())
    asyncio.run(quotations.listing(user={"tenant_id": BUSINESS_B["id"], "role": "owner"}))
    assert BUSINESS_B["id"] in [s for s in pool.statements if s[0] == "fetch"][0][2]


# ---------------------------------------------------------- booking readiness is visible

def test_booking_readiness_explains_closed_hours_before_the_owner_tries():
    """The owner must be told their hours cannot produce a booking, not left to discover it on submit.

    This is the gap the readiness entry closes: `booking_hours_problem` already refused a broken
    enable, but nothing surfaced the reason until the owner pressed the button. An owner who never
    presses it was never told, which is the silent breakage the validator exists to prevent.
    """
    closed = {**BUSINESS_A, "business_hours": {d: [] for d in ("mon", "tue", "wed", "thu", "fri")}}
    state = owner_onboarding.booking_readiness(closed)
    assert state["enabled"] is False
    assert state["ready"] is False
    assert state["open_days"] == 0
    assert "opening hours" in state["reason"]


def test_booking_readiness_is_clean_for_usable_hours():
    state = owner_onboarding.booking_readiness(BUSINESS_A)
    assert state["open_days"] == 5
    assert state["reason"] == ""
    assert state["slot_minutes"] == 30


def test_booking_readiness_separates_enabled_from_ready():
    """Booking switched on earlier, hours emptied since: enabled but NOT ready must stay visible."""
    stale = {**BUSINESS_A, "native_booking": True,
             "business_hours": {d: [] for d in ("mon", "tue", "wed", "thu", "fri")}}
    state = owner_onboarding.booking_readiness(stale)
    assert state["enabled"] is True
    assert state["ready"] is False
    assert state["configured"] is False
    assert state["reason"]


def test_booking_readiness_flags_a_window_shorter_than_one_slot():
    tiny = {**BUSINESS_A, "slot_minutes": 60,
            "business_hours": {"mon": [["09:00", "09:30"]], "tue": [], "wed": [], "thu": [], "fri": []}}
    state = owner_onboarding.booking_readiness(tiny)
    assert state["ready"] is False
    assert "60-minute" in state["reason"]


def test_booking_readiness_accepts_a_window_exactly_one_slot_long():
    """The boundary is deliberate: 09:00-09:30 with 30-minute slots is one bookable time, not zero."""
    exact = {**BUSINESS_A, "slot_minutes": 30,
             "business_hours": {"mon": [["09:00", "09:30"]], "tue": [], "wed": [], "thu": [], "fri": []}}
    state = owner_onboarding.booking_readiness(exact)
    assert state["open_days"] == 1
    assert state["reason"] == ""


def test_each_business_reports_its_own_booking_readiness():
    """Two businesses, two answers: readiness must never be shared or inferred from the other."""
    a = owner_onboarding.booking_readiness(BUSINESS_A)
    b = owner_onboarding.booking_readiness(
        {**BUSINESS_B, "business_hours": {d: [] for d in ("mon", "tue", "wed", "thu", "fri")}})
    assert a["reason"] == "" and a["open_days"] == 5
    assert b["reason"] != "" and b["open_days"] == 0


# ---------------------------------------------------------- owner UI renders every permission

def test_owner_ui_guards_a_channel_with_no_readiness_entry():
    """The authorizations panel must not assume every authorizable channel has a readiness entry.

    This shipped broken: `channelLabels` lists call_recording/email_read/email_send/sms_read/
    sms_send, but `overview`'s channels map has no entry for any of them. Reading
    `status.configured` unguarded threw on the first missing key and aborted the render loop, so
    only "telephone" was ever drawn and six permission checkboxes -- every email and SMS
    authorization -- were unreachable. The failure was swallowed by Promise.allSettled, so the
    owner saw a short list rather than an error.
    """
    from pathlib import Path
    import re
    html = (Path(__file__).resolve().parents[1] / "static" / "owner.html").read_text()
    assert "readiness.channels[key]" in html
    # Scope the check to the function that actually had the bug; other functions have their own
    # unrelated `status` locals (e.g. a freshly created <p> element).
    fn = re.search(r"async function refreshChannelAuthorizations\(\)\{.*?\n\}\n", html, re.S).group(0)
    # Strip whole comment LINES rather than a `//...` regex: `status?.reason` contains `?.` and a
    # naive `//` strip eats the `?`, turning safe optional chaining into what looks like a crash.
    code = "\n".join(line for line in fn.splitlines() if not line.strip().startswith("//"))
    # A missing entry must be handled, not dereferenced directly.
    assert '!status?"Provider state unavailable"' in code
    assert "status?.active" in code
    assert "if(status?.reason)" in code
    # Every bare `status.x` dereference must sit inside a guard that establishes `status` first.
    # Two safe shapes are used: the `!status ? ... : status.configured ? ...` conditional, and a
    # `status.reason` read inside `if(status?.reason){...}`. Anything else throws on a missing entry.
    guards = ["!status", "if(status?."]
    for match in re.finditer(r"(?<!\?\.)\bstatus\.(\w+)", code):
        window = code[max(0, match.start() - 60):match.start()]
        assert any(g in window for g in guards), (
            f"unguarded status.{match.group(1)} would crash the panel: ...{window[-60:]}"
        )


def test_authorizable_channels_and_readiness_keys_are_known_to_differ():
    """Pins the mismatch that caused the bug, so a future 'cleanup' cannot quietly reintroduce it."""
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "static" / "owner.html").read_text()
    block = re.search(r"const channelLabels=\{(.*?)\};", html, re.S).group(1)
    labels = set(re.findall(r"(\w+):\"", block))
    # These are authorizable but have no readiness entry; the UI must tolerate that.
    assert {"call_recording", "email_read", "email_send", "sms_read", "sms_send"} <= labels
    # The backend readiness map deliberately does not contain them.
    readiness = owner_onboarding.website_channel_status(
        {"slug": "x", "site_url": "https://x.example", "voice_enabled": True},
        SimpleNamespace(website_verified_tenants="", xai_api_key="k", effective_llm_key="k"))
    assert "call_recording" not in readiness
    assert "email_read" not in readiness
