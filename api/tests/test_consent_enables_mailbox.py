"""Consenting to read email must actually switch the inbox on.

A mailbox registered before the owner consented stays disabled, and nothing re-enabled it. The
customer granted permission, saw no error, and their mail was still refused — the operator then
fixed it with SQL. This pins the link between the owner's click and a working inbox.
"""
import asyncio

import pytest

from app import main
from app.channel_authorization import ChannelAuthorization


def _patch(monkeypatch, tenant, record=None, ensure=None):
    called = {"ensure": []}

    async def fake_record(tenant_id, actor_id, body):
        return {"channel": body.channel, "authorized": bool(body.authorized)}

    async def fake_tenant(tenant_id):
        return tenant

    async def fake_ensure(value):
        called["ensure"].append(value)
        if ensure:
            return await ensure(value)
        return value

    monkeypatch.setattr(main.owner_auth, "require_role", lambda user, role: None)
    monkeypatch.setattr(main.channel_authorization, "record_authorization", record or fake_record)
    monkeypatch.setattr(main.tenants, "get_by_id", fake_tenant)
    monkeypatch.setattr(main.reply_address, "ensure", fake_ensure)
    return called


def _call(channel="email_read", authorized=True):
    body = ChannelAuthorization(channel=channel, authorized=authorized, acknowledgement=True)
    return asyncio.run(main.owner_channel_authorization_update(
        body, {"tenant_id": "t1", "id": "u1", "slug": "acme"}))


def test_granting_email_consent_switches_the_inbox_on(monkeypatch):
    called = _patch(monkeypatch, {"id": "t1", "reply_address": "reply-abc@reply.trendibizz.com"})
    result = _call()
    assert len(called["ensure"]) == 1, "the mailbox must be re-enabled when the owner allows email"
    assert result["mailbox"] == "enabled"


def test_a_business_with_no_reply_address_is_left_alone(monkeypatch):
    called = _patch(monkeypatch, {"id": "t1", "reply_address": ""})
    result = _call()
    assert called["ensure"] == []
    assert "mailbox" not in result


def test_granting_an_unrelated_permission_does_not_touch_the_inbox(monkeypatch):
    called = _patch(monkeypatch, {"id": "t1", "reply_address": "reply-abc@reply.trendibizz.com"})
    _call(channel="telephone")
    assert called["ensure"] == []


def test_withdrawing_email_consent_does_not_silently_switch_it_back_on(monkeypatch):
    called = _patch(monkeypatch, {"id": "t1", "reply_address": "reply-abc@reply.trendibizz.com"})
    _call(authorized=False)
    assert called["ensure"] == []


def test_a_routing_failure_never_loses_the_owner_decision(monkeypatch):
    async def boom(value):
        raise RuntimeError("cloudflare unreachable")

    called = _patch(monkeypatch, {"id": "t1", "reply_address": "reply-abc@reply.trendibizz.com"},
                    ensure=boom)
    result = _call()
    assert result["authorized"] is True, "the consent is recorded whatever the network does"
    assert result["mailbox"] == "could not be re-enabled automatically"
    assert len(called["ensure"]) == 1
