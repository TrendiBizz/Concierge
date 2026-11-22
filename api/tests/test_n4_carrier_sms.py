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


def test_twilio_sms_is_disabled_and_routes_removed(monkeypatch):
    settings = Settings(sms_provider="twilio", twilio_account_sid="ACfixture", twilio_auth_token="test")
    monkeypatch.setattr(sms, "get_settings", lambda: settings)
    monkeypatch.setattr(sms.flood_guard, "memory_allow", lambda *a: True)
    assert not settings.sms_configured and not sms.sender_ready({})
    transport(monkeypatch, lambda req: pytest.fail("Twilio SMS must never send"))
    with pytest.raises(sms.SmsNotConfigured):
        asyncio.run(sms.send_sms("+64210000001", "hello"))
    paths = {r.path for r in telephony.router.routes}
    assert "/api/v1/sms/{public_key}" not in paths
    assert "/api/v1/sms/status/{outbox_id}" not in paths
    assert "/api/v1/smsgate/{public_key}" in paths


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
                assert not await sms_delivery.begin(oid, other, "smsgate")
                assert await sms_delivery.begin(oid, tenant, "smsgate")
                assert not await sms_delivery.begin(oid, tenant, "smsgate")
                await sms_delivery.accepted(oid, "smsgate", "gw-msg-1")
                assert not await sms_delivery.smsgate_receipt(other, "sms:delivered", {"messageId": "gw-msg-1"})
                assert await sms_delivery.smsgate_receipt(tenant, "sms:sent", {"messageId": "gw-msg-1"})
                assert await conn.fetchval("SELECT status FROM outbox WHERE id=$1", oid) == "awaiting_receipt"
                assert await sms_delivery.smsgate_receipt(tenant, "sms:delivered", {"messageId": "gw-msg-1"})
                row = await conn.fetchrow("SELECT * FROM outbox WHERE id=$1", oid)
                assert row["status"] == "sent" and row["sms_delivery_status"] == "delivered" and row["sent_at"]
                # Stale awaiting_receipt rows are held after 24 hours.
                await conn.execute("UPDATE outbox SET status='awaiting_receipt',sms_provider='smsgate',claimed_at=now()-interval '25 hours' WHERE id=$1", oid)
                await sms_delivery.reconcile()
                assert await conn.fetchval("SELECT status FROM outbox WHERE id=$1", oid) == "held"
        finally:
            await pool.execute('SET search_path TO public')
            await pool.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await pool.close()
    asyncio.run(run())
