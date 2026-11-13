"""Pause everything: the owner's own switch, and why suppression must return one shape.

Two things are pinned here.

1. The switch itself. While it is on, no model call produces an answer, nothing is queued to a
   customer, and inbound is still captured so the business does not lose a lead. It is per
   tenant: one customer pausing must never silence another.

2. The shape of a suppressed turn. Every caller reads `reply`, `lead_captured`, `booking_url`
   and `appointment` off the result. The human-takeover path returned only four keys, so
   `/api/v1/chat` raised a KeyError and answered the visitor with a 502 — a takeover looked like
   a broken website. That is why `suppressed()` exists and is tested.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import chat, main, outbox, tenant_pause

TENANT = {"id": "t1", "slug": "acme", "name": "Acme Ltd"}

ENDPOINT_READS = ("reply", "lead_captured", "booking_url", "appointment")


class _Pool:
    """Enough of asyncpg for these paths; any unexpected query raises so tests stay honest."""

    async def fetch(self, *a):
        return []

    def __init__(self, fetchrow=None, fetchval=None, execute=None):
        self._fetchrow = fetchrow
        self._fetchval = fetchval
        self.executed = []
        self._execute = execute

    async def fetchrow(self, *a):
        return self._fetchrow(*a) if callable(self._fetchrow) else self._fetchrow

    async def fetchval(self, *a):
        return self._fetchval(*a) if callable(self._fetchval) else self._fetchval

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if self._execute:
            return self._execute(sql, *args)
        return "OK"


# -- the switch ------------------------------------------------------------


def test_state_reports_paused_and_when(monkeypatch):
    monkeypatch.setattr(tenant_pause.db, "pool", lambda: _Pool(
        fetchrow={"paused_at": None, "paused_by": None}))
    assert asyncio.run(tenant_pause.state("t1")) == {"paused": False, "since": None, "by": None}


def test_state_reports_a_live_pause(monkeypatch):
    class Stamp:
        def isoformat(self):
            return "2026-11-13T03:00:00+00:00"

    monkeypatch.setattr(tenant_pause.db, "pool", lambda: _Pool(
        fetchrow={"paused_at": Stamp(), "paused_by": "owner@acme.nz"}))
    state = asyncio.run(tenant_pause.state("t1"))
    assert state["paused"] is True
    assert state["since"] == "2026-11-13T03:00:00+00:00"
    assert state["by"] == "owner@acme.nz"


def test_setting_paused_writes_both_columns(monkeypatch):
    pool = _Pool(fetchrow={"paused_at": None, "paused_by": None})
    monkeypatch.setattr(tenant_pause.db, "pool", lambda: pool)
    asyncio.run(tenant_pause.set_paused("t1", True, "owner@acme.nz"))
    sql, args = pool.executed[0]
    assert "paused_at=CASE WHEN $2" in sql and "paused_by=" in sql
    assert args == ("t1", True, "owner@acme.nz")


def test_a_tenant_already_loaded_as_paused_needs_no_query(monkeypatch):
    def explode():
        raise AssertionError("should not have queried")

    monkeypatch.setattr(tenant_pause.db, "pool", explode)
    assert asyncio.run(tenant_pause.is_paused({**TENANT, "paused_at": object()})) is True


def test_a_transient_read_error_does_not_silence_the_business(monkeypatch):
    """Failing closed would let one bad read stop every reply for that business."""
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(tenant_pause.db, "pool", boom)
    assert asyncio.run(tenant_pause.is_paused(TENANT)) is False


# -- a suppressed turn has one shape ---------------------------------------


def test_suppressed_carries_every_key_the_endpoint_reads():
    result = chat.suppressed("tenant_paused", 7, "thanks")
    for key in ENDPOINT_READS:
        assert key in result, f"{key} missing: the chat endpoint reads it and would 500"
    assert result["reply"] == "thanks" and result["suppressed"] is True


def test_a_human_takeover_returns_the_full_shape(monkeypatch):
    """The regression behind the 502: a takeover returned only four keys."""
    async def taken_over(*a, **k):
        return True

    monkeypatch.setattr(chat.casetimeline, "is_paused_for", taken_over)
    result = asyncio.run(chat.run_turn(TENANT, "sess-4", "chat", "hello"))
    assert result["suppressed"] is True and result["reason"] == "human_takeover"
    for key in ENDPOINT_READS:
        assert key in result, f"{key} missing: /api/v1/chat reads it and would answer 502"


def _quiet_patches(monkeypatch, paused=True, channel="chat"):
    calls = {"capture": [], "saved": [], "reached_model": False}

    async def not_taken_over(*a, **k):
        return False

    async def is_paused(tenant):
        return paused

    async def get_or_create(tenant, session_id, ch, page_url, utm):
        return 42

    async def save_message(conversation_id, role, text):
        calls["saved"].append((conversation_id, role, text))

    async def capture(tenant, kind, key, text, conversation_id=None):
        calls["capture"].append((kind, key, text))

    def reached(*a, **k):
        calls["reached_model"] = True
        raise AssertionError("the model path must not be reached while paused")

    monkeypatch.setattr(chat.casetimeline, "is_paused_for", not_taken_over)
    monkeypatch.setattr(chat.tenant_pause, "is_paused", is_paused)
    monkeypatch.setattr(chat.convo, "get_or_create", get_or_create)
    monkeypatch.setattr(chat.convo, "save_message", save_message)
    monkeypatch.setattr(chat.enquiries, "capture", capture)
    async def history(conversation_id):
        return []

    monkeypatch.setattr(chat, "_history", history)
    monkeypatch.setattr(chat, "retrieve", reached)
    return calls


def test_a_paused_chat_takes_the_message_and_says_something_humane(monkeypatch):
    calls = _quiet_patches(monkeypatch)
    result = asyncio.run(chat.run_turn(TENANT, "sess-1", "chat", "do you fix roofs?"))
    assert result["suppressed"] is True and result["reason"] == "tenant_paused"
    assert result["reply"] == tenant_pause.HOLDING_REPLY
    assert calls["capture"], "the enquiry must still be captured while paused"
    assert calls["saved"], "the visitor's own words must still be recorded"
    assert calls["reached_model"] is False


def test_a_paused_sms_gets_no_reply_because_that_would_be_a_send(monkeypatch):
    calls = _quiet_patches(monkeypatch, channel="sms")
    result = asyncio.run(chat.run_turn(TENANT, "sess-2", "sms", "hi", sender_phone="+64211234567"))
    assert result["suppressed"] is True
    assert result["reply"] == "", "an SMS reply is a send, and the owner asked for silence"
    assert calls["reached_model"] is False


def test_resumed_business_runs_normally(monkeypatch):
    calls = _quiet_patches(monkeypatch, paused=False)
    with pytest.raises(AssertionError, match="model path"):
        asyncio.run(chat.run_turn(TENANT, "sess-3", "chat", "hello"))
    assert calls["reached_model"] is True, "with the pause off the normal path runs"


# -- the endpoints ---------------------------------------------------------


def test_a_viewer_cannot_pause_the_business(monkeypatch):
    monkeypatch.setattr(main.tenant_pause, "set_paused", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a viewer must not reach the write")))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(main.owner_set_pause(
            main.PauseRequest(paused=True), {"tenant_id": "t1", "role": "viewer", "email": "v@a.nz"}))
    assert caught.value.status_code == 403


def test_the_owner_can_pause_and_is_recorded_by_email(monkeypatch):
    seen = {}

    async def fake_set(tenant_id, paused, by):
        seen.update(tenant_id=tenant_id, paused=paused, by=by)
        return {"paused": paused, "since": None, "by": by}

    monkeypatch.setattr(main.tenant_pause, "set_paused", fake_set)
    asyncio.run(main.owner_set_pause(
        main.PauseRequest(paused=True), {"tenant_id": "t1", "role": "owner", "email": "o@acme.nz"}))
    assert seen == {"tenant_id": "t1", "paused": True, "by": "o@acme.nz"}


# -- outbound --------------------------------------------------------------


def _deliver(monkeypatch, paused, kind="email_secretary_reply"):
    finished = []

    async def get_tenant(tenant_id):
        return {**TENANT, "email_auto_reply": True}

    async def is_paused(tenant):
        return paused

    async def finish(row_id, status, reason=""):
        finished.append((row_id, status, reason))

    async def send(*a, **k):
        finished.append(("sent", a[0]))

    async def authorised(*a, **k):
        return True

    class _Settings:
        smtp_from = "no-reply@trendibizz.com"
        sms_from = ""
        email_configured = True

        def __getattr__(self, name):  # any other flag the send path asks about
            return None

    monkeypatch.setattr(outbox, "get_settings", _Settings)
    monkeypatch.setattr(outbox.db, "pool", lambda: _Pool(fetchrow=None, fetchval=None))
    monkeypatch.setattr(outbox.tenants, "get_by_id", get_tenant)
    monkeypatch.setattr(outbox.tenant_pause, "is_paused", is_paused)
    monkeypatch.setattr(outbox, "_finish", finish)
    monkeypatch.setattr(outbox.mailer, "send_email", send)
    monkeypatch.setattr(outbox.channel_authorization, "is_authorized", authorised)

    row = {"id": 5, "tenant_id": "t1", "kind": kind, "channel": "email",
           "to_addr": "customer@example.nz", "subject": "Re: quote",
           "body": "Here is your quote.", "message_id": "<abc@trendibizz.com>",
           "campaign_id": None}
    asyncio.run(outbox._deliver(row))
    return finished


def test_a_queued_customer_email_is_not_sent_while_paused(monkeypatch):
    finished = _deliver(monkeypatch, paused=True)
    assert finished == [(5, "skipped", "tenant_paused")]


def test_the_owner_still_gets_their_own_alerts_while_paused(monkeypatch):
    finished = _deliver(monkeypatch, paused=True, kind="owner_alert")
    assert not any(entry[:3] == (5, "skipped", "tenant_paused") for entry in finished), \
        "a paused business still needs to know who tried to reach it"
    assert any(entry[0] == "sent" for entry in finished)


def test_nothing_is_skipped_when_not_paused(monkeypatch):
    finished = _deliver(monkeypatch, paused=False)
    assert any(entry[0] == "sent" for entry in finished)
