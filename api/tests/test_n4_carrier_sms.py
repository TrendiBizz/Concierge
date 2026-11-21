"""N4: mocked transport, real signed callbacks, and real Postgres receipt transitions. No SMS sent."""
import asyncio
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db, sms, sms_delivery
from app.config import Settings
from app.routers import telephony


@pytest.fixture
def gateway(monkeypatch):
    settings = Settings(sms_provider="smsgate", smsgate_base_url="https://sms.example",
                        smsgate_username="fixture", smsgate_password="fixture-password")
    monkeypatch.setattr(sms, "get_settings", lambda: settings)
    monkeypatch.setattr(sms.flood_guard, "memory_allow", lambda *a: True)
    return settings


def transport(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(sms.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(handler), **kw))


def test_hero_cannot_send_even_with_stale_environment(monkeypatch):
    settings = Settings(sms_provider="hero")
    monkeypatch.setattr(sms, "get_settings", lambda: settings)
    monkeypatch.setattr(sms.flood_guard, "memory_allow", lambda *a: True)
    assert not settings.sms_configured and not sms.sender_ready({})
    transport(monkeypatch, lambda req: pytest.fail("Hero must never receive SMS"))
    with pytest.raises(sms.SmsNotConfigured):
        asyncio.run(sms.send_sms("+64210000001", "hello"))


def test_own_sms_default_and_paired_phone_override(monkeypatch):
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    assert Settings(_env_file=None).sms_provider == "smsgate"
    settings = Settings(sms_provider="none")
    monkeypatch.setattr(sms, "get_settings", lambda: settings)
    monkeypatch.setattr(sms.flood_guard, "memory_allow", lambda *a: True)
    from app import device_sms
    enqueue = AsyncMock(return_value="phone-receipt")
    monkeypatch.setattr(device_sms, "enqueue", enqueue)
    tenant = {"id": "t", "sms_transport": "device", "sms_enabled": True, "sms_from": "+64210000002"}
    assert sms.sender_ready(tenant)
    assert asyncio.run(sms.send_sms("+64210000001", "hello", tenant=tenant, request_key="outbox:4", outbox_id=4)) == "phone-receipt"
    enqueue.assert_awaited_once_with(tenant, "+64210000001", "hello", "outbox:4", 4)


def test_smsgate_submission_is_durable_and_not_delivered(gateway, monkeypatch):
    begin = AsyncMock(return_value=True)
    accepted = AsyncMock()
    monkeypatch.setattr(sms_delivery, "begin", begin)
    monkeypatch.setattr(sms_delivery, "accepted", accepted)
    def handler(req):
        begin.assert_awaited_once_with(4, "t", "smsgate")
        assert req.url.host == "sms.example"
        return httpx.Response(202, json={"id": "gateway-id"})
    transport(monkeypatch, handler)
    assert asyncio.run(sms.send_sms("+64210000001", "hello", tenant={"id": "t"}, outbox_id=4)) == "gateway-id"
    accepted.assert_awaited_once_with(4, "smsgate", "gateway-id")


def test_timeout_is_uncertain_and_second_submission_is_prevented(gateway, monkeypatch):
    begin = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(sms_delivery, "begin", begin)
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("credential-shaped-provider-response", request=req)
    transport(monkeypatch, handler)
    for _ in range(2):
        with pytest.raises(sms.SmsUncertain) as error:
            asyncio.run(sms.send_sms("+64210000001", "hello", tenant={"id": "t"}, outbox_id=4))
        assert "credential-shaped" not in str(error.value)
    assert len(calls) == 1


def test_twilio_supplies_row_bound_callback(monkeypatch):
    settings = Settings(sms_provider="twilio", twilio_account_sid="ACfixture",
                        twilio_auth_token="test", twilio_from_number="+64210000002",
                        public_base_url="https://api.example")
    monkeypatch.setattr(sms, "get_settings", lambda: settings)
    seen = []
    def handler(req):
        seen.append(parse_qs(req.content.decode()))
        return httpx.Response(201, json={"sid": "SMfixture"})
    transport(monkeypatch, handler)
    assert asyncio.run(sms._send_twilio("+64210000001", "hello", None, outbox_id=4)) == "SMfixture"
    assert seen[0]["StatusCallback"] == ["https://api.example/api/v1/sms/status/4"]


def test_status_webhook_rejects_forgery_account_and_duplicate_fields(monkeypatch):
    settings = SimpleNamespace(twilio_account_sid="ACfixture", twilio_auth_token="test",
                               public_base_url="https://api.example")
    monkeypatch.setattr(telephony, "_main", lambda: SimpleNamespace(settings=settings))
    monkeypatch.setattr(sms, "provider", lambda: "twilio")
    receipt = AsyncMock(return_value=True)
    monkeypatch.setattr(sms_delivery, "twilio_receipt", receipt)
    app = FastAPI()
    app.include_router(telephony.router)
    client = TestClient(app)
    path = "/api/v1/sms/status/4"
    form = {"AccountSid": "ACfixture", "MessageSid": "SMfixture", "MessageStatus": "delivered", "To": "+64210000001"}
    import base64, hashlib, hmac
    def post(params, signed=True):
        value = settings.public_base_url + path + "".join(k + params[k] for k in sorted(params))
        signature = base64.b64encode(hmac.new(b"test", value.encode(), hashlib.sha1).digest()).decode()
        return client.post(path, content=urlencode(params), headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": signature if signed else "bad"})
    assert post(form, False).status_code == 403
    assert post({**form, "AccountSid": "other"}).status_code == 403
    receipt.assert_not_called()
    assert post(form).status_code == 200
    receipt.assert_awaited_once_with(4, form)
    assert client.post(path, content="MessageSid=a&MessageSid=b", headers={
        "Content-Type": "application/x-www-form-urlencoded"}).status_code == 400


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires test Postgres")
def test_real_database_receipt_ordering_scope_and_missing_receipts(monkeypatch):
    async def run():
        import asyncpg
        pool = await asyncpg.create_pool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=1)
        schema = "n4_" + uuid.uuid4().hex
        try:
            await pool.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await pool.execute(f'CREATE SCHEMA "{schema}"')
            async with pool.acquire() as conn:
                await conn.execute(f'SET search_path TO "{schema}",public')
                await conn.execute(Path(db.SCHEMA_PATH).read_text().replace("__DIM__", "1536"))
            # Use one acquired connection: schema remains isolated even if other suites run.
            async with pool.acquire() as conn:
                await conn.execute(f'SET search_path TO "{schema}",public')
                monkeypatch.setattr(db, "pool", lambda: conn)
                tenant = await conn.fetchval("INSERT INTO tenants(slug,name,public_key) VALUES('fixture','Fixture','pk') RETURNING id")
                other = uuid.uuid4()
                oid = await conn.fetchval("INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status) VALUES($1,'test','sms','+64210000001','hello','sending') RETURNING id", tenant)
                assert not await sms_delivery.begin(oid, other, "twilio")
                assert await sms_delivery.begin(oid, tenant, "twilio")
                assert not await sms_delivery.begin(oid, tenant, "twilio")
                form = {"MessageSid": "SMfixture", "MessageStatus": "delivered", "To": "+64210000001"}
                assert not await sms_delivery.twilio_receipt(oid, {**form, "To": "+64210000009"})
                assert await sms_delivery.twilio_receipt(oid, form)
                # Response bookkeeping and reordered/replayed callbacks cannot regress delivery.
                await sms_delivery.accepted(oid, "twilio", "SMfixture")
                assert await sms_delivery.twilio_receipt(oid, {**form, "MessageStatus": "sent"})
                assert not await sms_delivery.twilio_receipt(oid, {**form, "MessageSid": "other"})
                row = await conn.fetchrow("SELECT * FROM outbox WHERE id=$1", oid)
                assert row["status"] == "sent" and row["sms_delivery_status"] == "delivered" and row["sent_at"]
                await conn.execute("UPDATE outbox SET status='awaiting_receipt',sent_at=NULL,sms_delivery_status='queued' WHERE id=$1", oid)
                assert await sms_delivery.twilio_receipt(oid, {**form, "MessageStatus": "sent"})
                assert await conn.fetchval("SELECT status FROM outbox WHERE id=$1", oid) == "awaiting_receipt"
                assert await sms_delivery.twilio_receipt(oid, {**form, "MessageStatus": "queued"})
                assert await conn.fetchval("SELECT sms_delivery_status FROM outbox WHERE id=$1", oid) == "sent"
                assert await sms_delivery.twilio_receipt(oid, {**form, "MessageStatus": "undelivered"})
                assert await conn.fetchval("SELECT status FROM outbox WHERE id=$1", oid) == "failed"
                await conn.execute("UPDATE outbox SET status='awaiting_receipt',sms_provider='smsgate',claimed_at=now()-interval '25 hours' WHERE id=$1", oid)
                await sms_delivery.reconcile()
                assert await conn.fetchval("SELECT status FROM outbox WHERE id=$1", oid) == "held"
        finally:
            await pool.execute('SET search_path TO public')
            await pool.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await pool.close()
    asyncio.run(run())
