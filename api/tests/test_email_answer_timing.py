"""Generating an email is not evidence that its queued reply was sent."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import casetimeline, chat, outbox
from test_case_reply_scope import _run_check


def test_email_generation_keeps_the_message_unanswered(monkeypatch):
    monkeypatch.setattr(casetimeline, "is_paused_for", AsyncMock(return_value=False))
    monkeypatch.setattr(chat, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_run_llm", AsyncMock(return_value="Here is your answer"))
    monkeypatch.setattr(chat, "build_system_prompt", lambda *a: "Fixture")
    monkeypatch.setattr(chat.convo, "get_or_create", AsyncMock(return_value="conversation"))
    monkeypatch.setattr(chat.convo, "save_message", AsyncMock())
    monkeypatch.setattr(chat.owner_notifications, "queue", AsyncMock())
    monkeypatch.setattr(chat.db, "pool", lambda: SimpleNamespace(
        fetch=AsyncMock(return_value=[]), fetchval=AsyncMock(return_value=None)))
    stamp = AsyncMock()
    monkeypatch.setattr(casetimeline, "mark_replied", stamp)
    result = asyncio.run(chat.run_turn(
        {"id": "tenant", "name": "Fixture", "default_country_code": "64"},
        "email-session", "email", "Question", sender_email="alice@example.com"))
    assert result["reply"] == "Here is your answer"
    stamp.assert_not_awaited()


def test_only_successful_email_delivery_answers_the_recipient(monkeypatch):
    async def check(conn, tenant_id, alice, bob, outsider):
        tenant = {"id": tenant_id, "name": "Fixture", "email_auto_reply": True,
                  "default_country_code": "64"}
        monkeypatch.setattr(outbox, "get_settings", lambda: SimpleNamespace(email_configured=True))
        monkeypatch.setattr(outbox.tenants, "get_by_id", AsyncMock(return_value=tenant))
        monkeypatch.setattr(outbox.channel_authorization, "is_authorized", AsyncMock(return_value=True))
        monkeypatch.setattr(outbox, "is_opted_out", AsyncMock(return_value=False))
        monkeypatch.setattr(casetimeline, "is_paused_for", AsyncMock(return_value=False))
        monkeypatch.setattr(outbox, "_finish", AsyncMock())
        send = AsyncMock(side_effect=RuntimeError("mail server unavailable"))
        monkeypatch.setattr(outbox.mailer, "send_email", send)
        row = {"id": 1, "tenant_id": tenant_id, "kind": "email_secretary_reply",
               "channel": "email", "to_addr": "alice@example.com", "subject": "Re: Question",
               "body": "Here is your answer"}
        with pytest.raises(RuntimeError, match="mail server unavailable"):
            await outbox._deliver(row)
        assert await conn.fetchval("SELECT count(*) FROM case_events WHERE answered_at IS NOT NULL") == 0
        send.side_effect = None
        await outbox._deliver(row)
        rows = await conn.fetch("SELECT case_id,channel FROM case_events WHERE answered_at IS NOT NULL")
        assert [(r["case_id"], r["channel"]) for r in rows] == [(alice, "email")]
    _run_check(monkeypatch, check)
