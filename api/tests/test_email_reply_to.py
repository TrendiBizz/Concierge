"""Customer-visible email must carry the tenant reply address as Reply-To.

Only `owner_alert` used to get one, so a customer answering an auto-reply wrote to the
global admin@ inbox and the reply-<token> loop was bypassed (assessment 3.3).
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import casetimeline, outbox

REPLY = "reply-abc@trendibizz.com"


def _pool(suppressed: bool):
    pool = SimpleNamespace(
        execute=AsyncMock(return_value="UPDATE 1"),
        fetchval=AsyncMock(return_value=1 if suppressed else None),
    )
    return pool


def _patch(monkeypatch, suppressed=False, tenant_extra=None):
    tenant = {"id": "t1", "name": "Pukeko", "reply_address": REPLY,
              "default_country_code": "64", "email_auto_reply": True,
              **(tenant_extra or {})}
    monkeypatch.setattr(outbox, "get_settings",
                        lambda: SimpleNamespace(email_configured=True,
                                                smtp_from="admin@trendibizz.com"))
    monkeypatch.setattr(outbox.db, "pool", lambda: _pool(suppressed))
    monkeypatch.setattr(outbox.tenants, "get_by_id", AsyncMock(return_value=tenant))
    monkeypatch.setattr(outbox.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(outbox, "is_opted_out", AsyncMock(return_value=False))
    monkeypatch.setattr(outbox.suppressions, "is_suppressed", AsyncMock(return_value=suppressed))
    monkeypatch.setattr(casetimeline, "is_paused_for", AsyncMock(return_value=False))
    monkeypatch.setattr(casetimeline, "mark_replied", AsyncMock())
    finish = AsyncMock()
    monkeypatch.setattr(outbox, "_finish", finish)
    sent = {}

    async def capture(to_addr, subject, body, headers=None, from_name=None):
        sent["headers"] = headers or {}
        sent["to"] = to_addr

    monkeypatch.setattr(outbox.mailer, "send_email", capture)
    return finish, sent


def _row(kind: str):
    return {"id": 7, "tenant_id": "t1", "kind": kind, "channel": "email",
            "to_addr": "customer@example.com", "subject": "Re: your enquiry",
            "body": "Thanks for getting in touch."}


@pytest.mark.parametrize("kind", ["email_secretary_reply", "approved_reply", "owner_alert"])
def test_every_email_kind_carries_the_tenant_reply_to(monkeypatch, kind):
    finish, sent = _patch(monkeypatch)
    asyncio.run(outbox._deliver(_row(kind)))
    assert sent["headers"]["Reply-To"] == REPLY


def test_message_id_is_recorded_so_a_bounce_can_be_matched(monkeypatch):
    finish, sent = _patch(monkeypatch)
    asyncio.run(outbox._deliver(_row("email_secretary_reply")))
    assert sent["headers"]["Message-ID"].startswith("<") and "@" in sent["headers"]["Message-ID"]
    finish.assert_awaited_once_with(7, "sent")


def test_suppressed_address_is_never_sent_to(monkeypatch):
    finish, sent = _patch(monkeypatch, suppressed=True)
    asyncio.run(outbox._deliver(_row("email_secretary_reply")))
    finish.assert_awaited_once_with(7, "suppressed", "address_suppressed")
    assert sent == {}


def test_no_reply_address_means_no_reply_to_header(monkeypatch):
    finish, sent = _patch(monkeypatch, tenant_extra={"reply_address": ""})
    asyncio.run(outbox._deliver(_row("email_secretary_reply")))
    assert "Reply-To" not in sent["headers"]
