"""Inbound Worker ingress: refusals are audited, bounces never become drafts, limits come first."""
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import cloudflare_inbound

SECRET = "s" * 40
MAILBOX = {"tenant_id": "tenant-1", "recipient": "reply-abc@trendibizz.com"}


def _request(payload: dict) -> Request:
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    signature = cloudflare_inbound.signature(SECRET, stamp, body)
    headers = {
        b"x-concierge-timestamp": stamp.encode(),
        b"x-concierge-signature": signature.encode(),
        b"content-type": b"application/json",
    }
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": list(headers.items()), "client": ("1.2.3.4", 1)}, receive)


def _payload(**extra):
    base = {"message_id": "<m1@example.com>", "recipient": MAILBOX["recipient"],
            "sender": "customer@example.com", "subject": "Quote please",
            "text": "Hello, can you quote a deck?"}
    base.update(extra)
    return base


class FakePool:
    def __init__(self, counts=(0, 0)):
        self.counts = list(counts)
        self.executed = []
        self.fetches = []

    async def fetchrow(self, query, *args):
        return MAILBOX

    async def fetchval(self, query, *args):
        self.fetches.append(" ".join(query.split()))
        return self.counts.pop(0) if self.counts else 0

    async def execute(self, query, *args):
        self.executed.append(" ".join(query.split()))
        return "INSERT 0 1"

    async def fetch(self, query, *args):
        return []


def _patch(monkeypatch, pool=None, authorized=True):
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: SimpleNamespace(
        inbound_cloudflare_enabled=True, inbound_cloudflare_secret=SECRET))
    monkeypatch.setattr(cloudflare_inbound.db, "pool", lambda: pool or FakePool())
    monkeypatch.setattr(cloudflare_inbound.channel_authorization, "is_authorized",
                        AsyncMock(return_value=authorized))
    audits = []

    async def audit(tenant_id, draft_id, action, actor, detail=None):
        audits.append((action, detail))

    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "audit", audit)
    return audits


def test_blocked_sender_is_dropped_with_an_audit_row(monkeypatch):
    audits = _patch(monkeypatch)
    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "rule_for",
                        AsyncMock(return_value="block"))
    result = asyncio.run(cloudflare_inbound.handle(_request(_payload())))
    assert result == {"accepted": True, "dropped": "blocked"}
    assert audits and audits[0][0] == "inbound_blocked"
    assert audits[0][1]["sender"] == "customer@example.com"


def test_bounce_is_handled_before_the_consent_gate(monkeypatch):
    _patch(monkeypatch, authorized=False)
    recorded = AsyncMock(return_value={"suppressed": True, "closed": 1})
    monkeypatch.setattr(cloudflare_inbound.suppressions, "record_dsn", recorded)
    raw = b"multipart/report"
    import base64
    payload = _payload(sender="MAILER-DAEMON@example.net", subject="Undelivered Mail",
                       raw_b64=base64.b64encode(raw).decode())
    parsed = {"address": "dead@example.com", "status": "5.1.1", "hard": True,
              "original_message_id": "<outbox-1@x>", "action": "failed", "diagnostic": ""}
    monkeypatch.setattr(cloudflare_inbound.bounces, "parse", lambda _raw: parsed)
    result = asyncio.run(cloudflare_inbound.handle(_request(payload)))
    assert result == {"accepted": True, "dropped": "bounce"}
    recorded.assert_awaited_once()
    assert recorded.await_args.args[0] == "tenant-1"


def test_mailbox_rate_limit_is_checked_before_verification(monkeypatch):
    pool = FakePool(counts=(cloudflare_inbound.MAILBOX_HOURLY_LIMIT, 0))
    _patch(monkeypatch, pool=pool)
    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "rule_for", AsyncMock(return_value=None))
    verified = AsyncMock()
    monkeypatch.setattr(cloudflare_inbound.email_auth, "verify", verified)
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(cloudflare_inbound.handle(_request(_payload(raw_b64="Zm9v"))))
    assert excinfo.value.status_code == 429
    verified.assert_not_awaited()


def test_hourly_limit_counts_the_mailbox_not_the_tenant(monkeypatch):
    pool = FakePool(counts=(0, 0))
    _patch(monkeypatch, pool=pool)
    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "rule_for", AsyncMock(return_value=None))
    monkeypatch.setattr(cloudflare_inbound.inbound_email, "ingest_verified",
                        AsyncMock(return_value={"id": 1}))
    asyncio.run(cloudflare_inbound.handle(_request(_payload())))
    # The limit counts the recipient mailbox; a tenant-wide count was the old bug.
    assert any("lower(recipient)=lower($2)" in query for query in pool.fetches)


def test_envelope_sender_is_carried_into_the_audit_detail(monkeypatch):
    """From is what we display; the envelope is kept because From != envelope is a
    spoofing signal, and an ESP relay puts its bounce address in the envelope."""
    _patch(monkeypatch)
    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "rule_for", AsyncMock(return_value=None))
    ingest = AsyncMock(return_value={"id": 1})
    monkeypatch.setattr(cloudflare_inbound.inbound_email, "ingest_verified", ingest)
    asyncio.run(cloudflare_inbound.handle(
        _request(_payload(envelope_from="bounces-1@send.trendibizz.com"))))
    assert ingest.await_args.kwargs["envelope_from"] == "bounces-1@send.trendibizz.com"


def test_unknown_payload_fields_are_rejected(monkeypatch):
    _patch(monkeypatch)
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(cloudflare_inbound.handle(_request(_payload(surprise="x"))))
    assert excinfo.value.status_code == 400


def test_oversized_envelope_sender_is_rejected(monkeypatch):
    _patch(monkeypatch)
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(cloudflare_inbound.handle(_request(_payload(envelope_from="a" * 400))))
    assert excinfo.value.status_code == 400
