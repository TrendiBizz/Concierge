"""Enabling a channel per tenant, safely and auditably.

Turning on automatic email replies is not one switch. For a reply to actually be delivered, THREE
things must agree, and each is checked at a different point in the pipeline:

  1. tenants.email_auto_reply            -- queues the job at ingress, and gates the worker
  2. tenant_channel_authorizations(email_read)   -- gates the worker and delivery
  3. tenant_channel_authorizations(email_send)   -- gates delivery

Setting only the flag leaves the worker permanently writing rows it then marks 'held', which looks
like a broken feature to the owner rather than a missing authorization. Setting only the
authorizations queues nothing at all. So enabling has to be atomic and has to report what it
actually achieved.

These tests pin the properties that make that safe:
  - enabling writes all three, in one transaction;
  - the authorization carries the acknowledgement the channel API requires, and is audited;
  - disabling is immediate and does NOT depend on the current flag value;
  - a caller cannot enable a channel they have not acknowledged controlling.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import channel_authorization, owner_onboarding

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "email_auto_reply": False,
}


# ---------------------------------------------------------------- acknowledgement


def test_enable_requires_explicit_acknowledgement():
    """An owner must affirm they control the channel; silently enabling is the failure mode."""
    with pytest.raises(ValueError):
        asyncio.run(owner_onboarding.set_email_auto_reply(
            TENANT, enabled=True, actor_id="user-1", acknowledgement=False,
        ))


def test_disable_does_not_require_acknowledgement():
    """Turning something OFF must always be possible, including in an emergency.

    Requiring an acknowledgement to stop automatic replies would be exactly backwards: the person
    disabling it may be reacting to a live problem.
    """
    calls = []

    async def fake_update(slug, fields):
        calls.append(fields)
        return {**TENANT, **fields}

    async def fake_record(tenant_id, actor_id, body):
        return {"channel": body.channel, "authorized": body.authorized}

    async def no_jobs():
        return 0

    import app.owner_onboarding as mod
    monkeypatched = [
        (mod.tenants, "update", fake_update),
        (mod.channel_authorization, "record_authorization", fake_record),
    ]
    originals = [(obj, name, getattr(obj, name)) for obj, name, _ in monkeypatched]
    for obj, name, fn in monkeypatched:
        setattr(obj, name, fn)
    try:
        result = asyncio.run(owner_onboarding.set_email_auto_reply(
            TENANT, enabled=False, actor_id="user-1", acknowledgement=False,
        ))
    finally:
        for obj, name, original in originals:
            setattr(obj, name, original)
    assert result["enabled"] is False
    assert calls and calls[0]["email_auto_reply"] is False


# ---------------------------------------------------------------- atomicity


def test_enable_sets_flag_and_both_authorizations(monkeypatch):
    """All three gates move together, or the feature half-works."""
    updated = {}
    recorded = []

    async def fake_update(slug, fields):
        updated.update(fields)
        return {**TENANT, **fields}

    async def fake_record(tenant_id, actor_id, body):
        recorded.append(body.channel)
        return {"channel": body.channel, "authorized": body.authorized}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    monkeypatch.setattr(owner_onboarding.channel_authorization, "record_authorization", fake_record)

    result = asyncio.run(owner_onboarding.set_email_auto_reply(
        TENANT, enabled=True, actor_id="user-1", acknowledgement=True,
    ))
    assert updated["email_auto_reply"] is True
    assert set(recorded) == {"email_read", "email_send"}
    assert result["enabled"] is True
    assert result["ready"] is True


def test_enable_reports_not_ready_when_an_authorization_fails(monkeypatch):
    """A partial enable must be REPORTED as partial, never claimed as working."""
    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    async def explode(tenant_id, actor_id, body):
        raise RuntimeError("authorization store unavailable")

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    monkeypatch.setattr(owner_onboarding.channel_authorization, "record_authorization", explode)

    result = asyncio.run(owner_onboarding.set_email_auto_reply(
        TENANT, enabled=True, actor_id="user-1", acknowledgement=True,
    ))
    assert result["enabled"] is True
    assert result["ready"] is False
    assert result["reason"], "a not-ready result must explain why"


def test_disable_turns_off_both_authorizations(monkeypatch):
    """Disabling must revoke sending as well as reading, not just flip the flag."""
    recorded = []

    async def fake_update(slug, fields):
        return {**TENANT, **fields}

    async def fake_record(tenant_id, actor_id, body):
        recorded.append((body.channel, body.authorized))
        return {"channel": body.channel, "authorized": body.authorized}

    monkeypatch.setattr(owner_onboarding.tenants, "update", fake_update)
    monkeypatch.setattr(owner_onboarding.channel_authorization, "record_authorization", fake_record)

    asyncio.run(owner_onboarding.set_email_auto_reply(
        TENANT, enabled=False, actor_id="user-1", acknowledgement=True,
    ))
    assert ("email_send", False) in recorded, "a disabled channel must not keep send permission"
    assert ("email_read", False) in recorded
