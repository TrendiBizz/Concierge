"""Behavioral regression tests for Audit PR 3: SMS, paired-phone, smsgate & missed-call fixes."""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import (
    asterisk_bridge,
    device_sms,
    missed_calls,
    outbox,
    owner_notifications,
    sms,
    sms_delivery,
    sms_inbox,
)
from app.routers import telephony


def test_missed_calls_uses_sms_send_and_matches_call_sid(monkeypatch):
    """evaluate_call checks 'sms_send' (not 'sms') and matches conversations by call_sid when session_id is NULL."""
    checked_channels = []
    queried_ids = []

    class Pool:
        async def fetchval(self, sql, *args):
            if "FROM messages m" in sql:
                queried_ids.append(args[1])
                return 0
            return 0

        async def execute(self, sql, *args):
            return "INSERT 0 1"

    async def fake_auth(tenant_id, channel):
        checked_channels.append(channel)
        return channel == "sms_send"

    queued = []

    async def fake_enqueue(*args, **kwargs):
        queued.append((args, kwargs))
        return True

    async def fake_capture(*args, **kwargs):
        return {"id": None}

    monkeypatch.setattr(missed_calls.db, "pool", lambda: Pool())
    monkeypatch.setattr(missed_calls.channel_authorization, "is_authorized", fake_auth)
    monkeypatch.setattr(missed_calls.outbox, "enqueue", fake_enqueue)
    monkeypatch.setattr(missed_calls.enquiries, "capture", fake_capture)

    tenant = {
        "id": uuid.uuid4(),
        "slug": "test-biz",
        "missed_call_textback": True,
        "sms_enabled": True,
        "timezone": "Pacific/Auckland",
        "booking_url": "",
    }
    now = datetime.now(timezone.utc)
    call = {
        "call_sid": "ast:1234",
        "tenant_id": tenant["id"],
        "session_id": None,
        "from_number": "0211234567",
        "to_number": "+6498880000",
        "status": "completed",
        "started_at": now - timedelta(seconds=5),
        "ended_at": now,
    }
    res = asyncio.run(missed_calls.evaluate_call(tenant, call))
    assert checked_channels == ["sms_send"]
    assert queried_ids == [["ast:1234"]]
    assert res["action"] == "text"
    assert len(queued) == 1


def test_missed_calls_answered_asterisk_call_skipped(monkeypatch):
    """When caller had turns under call_sid (with session_id=None) and call >= 20s, skip as answered."""
    class Pool:
        async def fetchval(self, sql, *args):
            if "FROM messages m" in sql:
                assert "ast:answered" in args[1]
                return 2
            return 0

        async def execute(self, sql, *args):
            return "INSERT 0 1"

    monkeypatch.setattr(missed_calls.db, "pool", lambda: Pool())
    monkeypatch.setattr(missed_calls.channel_authorization, "is_authorized", AsyncMock(return_value=True))

    tenant = {
        "id": uuid.uuid4(),
        "slug": "test-biz",
        "missed_call_textback": True,
        "sms_enabled": True,
        "timezone": "Pacific/Auckland",
    }
    now = datetime.now(timezone.utc)
    call = {
        "call_sid": "ast:answered",
        "tenant_id": tenant["id"],
        "session_id": None,
        "from_number": "+64211234567",
        "to_number": "+6498880000",
        "status": "completed",
        "started_at": now - timedelta(seconds=60),
        "ended_at": now,
    }
    res = asyncio.run(missed_calls.evaluate_call(tenant, call))
    assert res == {"action": "skip", "reason": "call_was_answered"}


def test_device_sms_late_receipt_reconciles_failed_outbox(monkeypatch):
    """A late 'sent' receipt for an 'uncertain' job reconciles the outbox row from 'failed' back to 'sent'."""
    executed = []
    job_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    device_id = uuid.uuid4()

    class Pool:
        def __init__(self):
            self.fetchrow_calls = 0

        async def fetchrow(self, sql, *args):
            self.fetchrow_calls += 1
            if self.fetchrow_calls == 1:
                return None  # not 'claimed' anymore
            if self.fetchrow_calls == 2:
                return {"status": "uncertain", "receipt": ""}
            return {"outbox_id": 42}

        async def execute(self, sql, *args):
            executed.append((sql, args))
            return "UPDATE 1"

    pool = Pool()
    monkeypatch.setattr(device_sms.db, "pool", lambda: pool)
    body = device_sms.Receipt(job_id=job_id, status="sent", receipt="msg-receipt-99")
    device = {"id": device_id, "tenant_id": tenant_id, "from_number": "+64210000000"}
    res = asyncio.run(device_sms.receipt(body, device))
    assert res == {"ok": True}
    outbox_updates = [item for item in executed if "UPDATE outbox SET status=$3" in item[0]]
    assert len(outbox_updates) == 1
    sql, args = outbox_updates[0]
    assert args[0] == 42
    assert args[2] == "sent"
    assert args[4] is True  # from_uncertain flag enables reconciling failed outbox row


def test_device_sms_inbound_handles_unauthorized_sms_send_without_500(monkeypatch):
    """Inbound device SMS does not 500 when sms_send is not authorized or reply exceeds 1500 chars."""
    enqueued = []

    class Pool:
        async def fetchval(self, sql, *args):
            return "m-1"

        async def execute(self, sql, *args):
            return "UPDATE 1"

    async def fake_auth(tenant_id, channel):
        return channel == "sms_read"  # sms_send is False

    async def fake_enqueue(*args, **kwargs):
        enqueued.append((args, kwargs))

    monkeypatch.setattr(device_sms.db, "pool", lambda: Pool())
    monkeypatch.setattr(device_sms.channel_authorization, "is_authorized", fake_auth)
    monkeypatch.setattr(device_sms.tenants, "get_by_id", AsyncMock(return_value={"id": uuid.uuid4(), "slug": "demo"}))
    monkeypatch.setattr(device_sms, "enqueue", fake_enqueue)

    from app import main as app_main
    monkeypatch.setattr(app_main, "_sms_reply", AsyncMock(return_value="x" * 2000))

    body = device_sms.Incoming(message_id="m-1", sender="+64211234567", to="+64219999999", body="Hello")
    device = {"id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "from_number": "+64219999999"}
    res = asyncio.run(device_sms.inbound(body, device))
    assert res == {"ok": True}
    assert enqueued == []


def test_smsgate_inbound_rejects_device_transport_and_handles_delivery_receipt(monkeypatch):
    """smsgate_inbound handles sms:delivered receipts and rejects sms:received for device-transport tenants."""
    receipt_calls = []

    async def fake_smsgate_receipt(tenant_id, event, payload):
        receipt_calls.append((tenant_id, event, payload))
        return True

    tenant = {
        "id": uuid.uuid4(),
        "slug": "demo",
        "sms_enabled": True,
        "sms_transport": "device",
        "timezone": "Pacific/Auckland",
    }
    monkeypatch.setattr(telephony.tenants, "get_by_key", AsyncMock(return_value=tenant))
    monkeypatch.setattr(telephony.sms, "provider", lambda: "smsgate")
    monkeypatch.setattr(telephony.sms, "validate_smsgate_signature", lambda *a: True)
    monkeypatch.setattr(sms_delivery, "smsgate_receipt", fake_smsgate_receipt)
    monkeypatch.setattr(telephony._main().settings, "smsgate_signing_key", "test-secret")

    def make_req(payload_dict):
        raw = json.dumps(payload_dict).encode()
        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}
        scope = {"type": "http", "method": "POST", "path": "/api/v1/smsgate/pk", "headers": []}
        return Request(scope, receive)

    # 1. sms:delivered updates delivery status
    res = asyncio.run(telephony.smsgate_inbound("pk", make_req({"event": "sms:delivered", "payload": {"messageId": "sg-1"}})))
    assert res == {"ok": True}
    assert len(receipt_calls) == 1
    assert receipt_calls[0][1] == "sms:delivered"

    # 2. sms:received rejected for device-transport tenant
    with pytest.raises(HTTPException) as exc:
        asyncio.run(telephony.smsgate_inbound("pk", make_req({"event": "sms:received", "payload": {"sender": "+64211234567", "message": "hi"}})))
    assert exc.value.status_code == 403


def test_sms_inbox_reply_does_not_takeover_on_send_failure(monkeypatch):
    """Owner SMS reply does not activate human takeover if sms.send_sms raises SmsRejected."""
    takeover_called = []

    async def fake_takeover(*args, **kwargs):
        takeover_called.append(True)

    monkeypatch.setattr(sms_inbox.tenants, "get_by_id", AsyncMock(return_value={"id": uuid.uuid4(), "slug": "demo"}))
    monkeypatch.setattr(sms_inbox, "_conversation", AsyncMock(return_value={"id": uuid.uuid4(), "session_id": "sms64211234567"}))
    monkeypatch.setattr(sms_inbox.outbox, "is_opted_out", AsyncMock(return_value=False))
    monkeypatch.setattr(sms_inbox.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(sms_inbox, "_set_takeover", fake_takeover)
    monkeypatch.setattr(sms_inbox.sms, "send_sms", AsyncMock(side_effect=sms.SmsRejected("rejected")))

    user = {"id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "role": "owner", "email": "owner@example.com"}
    body = sms_inbox.Reply(text="Hi", request_id=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sms_inbox.reply(uuid.uuid4(), body, user))
    assert exc.value.status_code == 409
    assert takeover_called == []


def test_owner_notifications_sms_reliable_uses_tenant_country_code(monkeypatch):
    """Local NZ number 021... normalizes to +6421... using tenant timezone."""
    monkeypatch.setattr(owner_notifications.channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(owner_notifications, "sms_unconfirmable", AsyncMock(return_value=False))
    tenant = {
        "id": uuid.uuid4(),
        "sms_enabled": True,
        "notify_phone": "021 123 4567",
        "default_country_code": "64",
    }
    res = asyncio.run(owner_notifications.sms_reliable(object(), tenant))
    assert res == ("sms", "+64211234567")


def test_outbox_reconcile_uses_job_created_at_and_expires_null_outbox_jobs(monkeypatch):
    """reconcile_stale_device_sms checks j.created_at and expires outbox_id IS NULL jobs."""
    queries = []

    class Pool:
        async def fetch(self, sql, *args):
            queries.append(sql)
            return []

        async def execute(self, sql, *args):
            queries.append(sql)
            return "UPDATE 0"

    monkeypatch.setattr(outbox.db, "pool", lambda: Pool())
    asyncio.run(outbox.reconcile_stale_device_sms())
    assert any("j.created_at < now()" in q for q in queries)
    assert any("outbox_id IS NULL" in q for q in queries)
