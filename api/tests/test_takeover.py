"""Human takeover and cross-channel reply suppression.

The requirement, in the audit's words: "Provide human takeover that immediately prevents further
automatic replies." Before this, nothing enforced it. An owner could personally answer a customer,
and the assistant would carry on replying to that same person over SMS and email as though the
conversation had never happened.

Two distinct points have to hold the line, and one is not enough:
  - the turn itself (chat.run_turn), so a new inbound message gets no AI answer;
  - delivery time (outbox._deliver), because a reply queued BEFORE the takeover would otherwise
    still go out afterwards. Checking only at queue time leaves that window open.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import casetimeline, chat, outbox

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "default_country_code": "64",
    "email_auto_reply": True,
    "sms_from": "+6421555000",
}


# ---------------------------------------------------------------- turn-time suppression


def test_turn_is_suppressed_when_the_case_is_paused(monkeypatch):
    """A paused case must produce no AI reply at all."""
    async def paused(tenant_id, *, phone="", email="", default_cc="1"):
        return True

    monkeypatch.setattr(casetimeline, "is_paused_for", paused, raising=False)
    monkeypatch.setattr(chat, "casetimeline", casetimeline, raising=False)
    sent = AsyncMock()
    monkeypatch.setattr(chat.llm, "complete", sent)

    result = asyncio.run(chat.run_turn(
        TENANT, "sms6421555123", "sms", "hello again",
        sender_phone="+6421555123", dry_run=False,
    ))
    assert result["suppressed"] is True
    assert result["reply"] == ""
    sent.assert_not_awaited()


def test_turn_proceeds_when_the_case_is_not_paused(monkeypatch):
    """The guard must not block ordinary traffic."""
    async def not_paused(tenant_id, *, phone="", email="", default_cc="1"):
        return False

    monkeypatch.setattr(casetimeline, "is_paused_for", not_paused, raising=False)
    monkeypatch.setattr(chat, "casetimeline", casetimeline, raising=False)
    monkeypatch.setattr(chat.llm, "complete",
                        AsyncMock(return_value=SimpleNamespace(content="Sure!", tool_calls=None)))
    monkeypatch.setattr(chat, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat.convo, "get_or_create", AsyncMock(return_value="conv-1"))
    monkeypatch.setattr(chat.convo, "save_message", AsyncMock())
    monkeypatch.setattr(chat.enquiries, "capture", AsyncMock())
    monkeypatch.setattr(chat, "_save_assistant", AsyncMock(), raising=False)
    monkeypatch.setattr(chat.convo, "set_pending_booking", AsyncMock(), raising=False)
    monkeypatch.setattr(chat.casetimeline, "mark_replied", AsyncMock(), raising=False)
    # The post-reply dialogue record reads the conversation back; not this test's subject.
    monkeypatch.setattr(chat.db, "pool", lambda: SimpleNamespace(
        fetch=AsyncMock(return_value=[]), fetchval=AsyncMock(return_value=None)))

    result = asyncio.run(chat.run_turn(
        TENANT, "sms6421555123", "sms", "hello",
        sender_phone="+6421555123", dry_run=False,
    ))
    assert result.get("suppressed") is not True
    assert result["reply"] == "Sure!"


def test_turn_is_not_suppressed_during_a_dry_run(monkeypatch):
    """A dry run must still execute, or eval scenarios would silently stop testing anything."""
    async def paused(tenant_id, *, phone="", email="", default_cc="1"):
        return True

    monkeypatch.setattr(casetimeline, "is_paused_for", paused, raising=False)
    monkeypatch.setattr(chat, "casetimeline", casetimeline, raising=False)
    monkeypatch.setattr(chat.llm, "complete",
                        AsyncMock(return_value=SimpleNamespace(content="Dry", tool_calls=None)))
    monkeypatch.setattr(chat, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat.convo, "get_or_create", AsyncMock(return_value="conv-1"))
    monkeypatch.setattr(chat.convo, "save_message", AsyncMock())

    result = asyncio.run(chat.run_turn(
        TENANT, "sms6421555123", "sms", "hello",
        sender_phone="+6421555123", dry_run=True,
    ))
    assert result.get("suppressed") is not True


def test_unknown_identity_is_never_treated_as_paused(monkeypatch):
    """No usable identifier means no case, and no case must not mean 'suppressed'."""
    async def none_case(tenant_id, *, phone="", email="", default_cc="1"):
        return False

    monkeypatch.setattr(casetimeline, "is_paused_for", none_case, raising=False)
    monkeypatch.setattr(chat, "casetimeline", casetimeline, raising=False)
    monkeypatch.setattr(chat, "casetimeline", casetimeline, raising=False)
    assert casetimeline.case_key("", "") is None


# ---------------------------------------------------------------- delivery-time suppression


def test_queued_reply_is_skipped_after_takeover(monkeypatch):
    """A reply queued before the owner took over must not be delivered after.

    This is the window that turn-time checking alone cannot close.
    """
    monkeypatch.setattr(outbox, "get_settings", lambda: SimpleNamespace(
        email_configured=False, sms_provider="none", device_sms_enabled=False))
    monkeypatch.setattr(outbox.tenants, "get_by_id",
                        AsyncMock(return_value={**TENANT, "sms_enabled": True}))

    async def paused(tenant_id, *, phone="", email="", default_cc="1"):
        return True

    monkeypatch.setattr(casetimeline, "is_paused_for", paused, raising=False)
    monkeypatch.setattr(outbox, "casetimeline", casetimeline, raising=False)
    monkeypatch.setattr(outbox.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(outbox, "is_opted_out", AsyncMock(return_value=False))

    finish = AsyncMock()
    monkeypatch.setattr(outbox, "_finish", finish)
    send = AsyncMock()
    monkeypatch.setattr(outbox, "send_sms", send, raising=False)
    monkeypatch.setattr(outbox.sms, "send_sms", send, raising=False)

    asyncio.run(outbox._deliver({
        "id": 1, "tenant_id": TENANT["id"], "kind": "speed_to_lead",
        "channel": "sms", "to_addr": "+6421555123",
    }))
    finish.assert_awaited()
    reason = finish.await_args.args[2]
    assert "takeover" in reason
    send.assert_not_awaited()


def test_owner_alerts_are_never_suppressed_by_takeover(monkeypatch):
    """Takeover silences replies TO THE CUSTOMER, never alerts TO THE OWNER.

    Suppressing owner alerts would hide the very message the owner needs to act on.
    """
    monkeypatch.setattr(outbox, "get_settings", lambda: SimpleNamespace(
        email_configured=False, sms_provider="none", device_sms_enabled=False))
    monkeypatch.setattr(outbox.tenants, "get_by_id", AsyncMock(return_value=dict(TENANT)))

    async def paused(tenant_id, *, phone="", email="", default_cc="1"):
        return True

    monkeypatch.setattr(casetimeline, "is_paused_for", paused, raising=False)
    monkeypatch.setattr(outbox, "casetimeline", casetimeline, raising=False)
    finish = AsyncMock()
    monkeypatch.setattr(outbox, "_finish", finish)
    mail = AsyncMock()
    monkeypatch.setattr(outbox.mailer, "send_email", mail)

    asyncio.run(outbox._deliver({
        "id": 2, "tenant_id": TENANT["id"], "kind": "owner_alert",
        "channel": "email", "to_addr": "owner@example.com", "subject": "s", "body": "b",
    }))
    assert not any("takeover" in str(c.args) for c in finish.await_args_list)


# ---------------------------------------------------------------- cross-channel bookkeeping


def test_mark_answered_without_source_key_clears_the_channel():
    """A reply knows the customer it answers, not the provider message id that prompted it.

    Regression: mark_replied only stamped an answer when it had a source_key, which the reply path
    never has, so the unified timeline kept reporting the customer's message as unanswered forever.
    """
    executed = []

    async def fake_execute(sql, *args):
        executed.append((sql, args))
        return "UPDATE 1"

    from app import db as _db
    original = _db._pool
    _db._pool = SimpleNamespace(execute=fake_execute)
    try:
        n = asyncio.run(casetimeline.mark_answered(TENANT["id"], channel="sms"))
    finally:
        _db._pool = original
    assert n == 1
    sql, args = executed[0]
    assert "source_key = $3" not in sql, "channel-wide answer must not require a source_key"
    assert args == (TENANT["id"], "sms")


def test_mark_answered_with_a_source_key_stays_precise():
    """When a source key IS known, only that one message is stamped."""
    executed = []

    async def fake_execute(sql, *args):
        executed.append((sql, args))
        return "UPDATE 1"

    from app import db as _db
    original = _db._pool
    _db._pool = SimpleNamespace(execute=fake_execute)
    try:
        asyncio.run(casetimeline.mark_answered(TENANT["id"], channel="sms", source_key="msg-1"))
    finally:
        _db._pool = original
    sql, args = executed[0]
    assert "source_key = $3" in sql
    assert args == (TENANT["id"], "sms", "msg-1")


def test_mark_answered_with_neither_key_is_a_noop():
    """No channel and no source key means nothing to stamp; it must not touch the database."""
    from app import db as _db
    original = _db._pool
    _db._pool = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("should not query")))
    try:
        assert asyncio.run(casetimeline.mark_answered(TENANT["id"])) == 0
    finally:
        _db._pool = original


def test_suppressed_email_turn_queues_nothing(monkeypatch):
    """A suppressed turn must not queue an EMPTY-BODY email to the customer.

    Regression: chat.run_turn correctly returns an empty reply when the owner has taken over, but
    the email secretary queued that empty string as a reply anyway and marked the draft discarded.
    """
    from app import email_secretary

    jobs = [{"id": 1, "tenant_id": TENANT["id"], "source_key": "k1",
             "sender": "hana@example.com", "subject": "Quote", "body": "How much?"}]
    queued = []

    async def fake_fetch(sql, *args):
        return jobs

    statements = []

    async def fake_execute(sql, *args):
        statements.append((sql, args))
        return "UPDATE 1"

    async def fake_fetchval(sql, *args):
        return "draft"

    monkeypatch.setattr(email_secretary.tenants, "get_by_id", AsyncMock(return_value=dict(TENANT)))
    monkeypatch.setattr(email_secretary.channel_authorization, "is_authorized",
                        AsyncMock(return_value=True))
    monkeypatch.setattr(email_secretary.db, "pool", lambda: SimpleNamespace(
        fetch=fake_fetch, execute=fake_execute, fetchval=fake_fetchval))
    # The turn reports suppression, exactly as the real guard does.
    monkeypatch.setattr(email_secretary.chat, "run_turn",
                        AsyncMock(return_value={"reply": "", "suppressed": True}))

    asyncio.run(email_secretary.process_once())

    assert not any("INSERT INTO outbox" in sql for sql, _ in statements), \
        "a suppressed turn queued a reply"
    held = [(sql, args) for sql, args in statements
            if "email_secretary_jobs SET status" in sql]
    assert held, "the job should have been updated"
    held_sql, held_args = held[0]
    assert "'held'" in held_sql, f"the job should be held, not sent or failed: {held_sql!r}"
    assert "takeover" in held_args[1].lower(), f"expected a takeover reason, got {held_args[1]!r}"


def test_empty_reply_never_reaches_the_outbox(monkeypatch):
    """Defence in depth: even a non-suppressed empty reply must not be queued."""
    from app import email_secretary

    queued = []

    async def fake_fetch(sql, *args):
        return [{"id": 1, "tenant_id": TENANT["id"], "source_key": "k1",
                 "sender": "hana@example.com", "subject": "Quote", "body": "How much?"}]

    statements = []

    async def fake_execute(sql, *args):
        statements.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(email_secretary.tenants, "get_by_id", AsyncMock(return_value=dict(TENANT)))
    monkeypatch.setattr(email_secretary.channel_authorization, "is_authorized",
                        AsyncMock(return_value=True))
    monkeypatch.setattr(email_secretary.db, "pool", lambda: SimpleNamespace(
        fetch=fake_fetch, execute=fake_execute, fetchval=AsyncMock(return_value="draft")))
    monkeypatch.setattr(email_secretary.chat, "run_turn",
                        AsyncMock(return_value={"reply": "   ", "suppressed": False}))

    asyncio.run(email_secretary.process_once())
    assert statements, "expected the job to be marked held"
    # 'held' is a SQL literal, not a bound parameter, so assert against the statement.
    assert any("'held'" in sql for sql, _ in statements), \
        f"expected a held status, got {statements[0][0]!r}"
