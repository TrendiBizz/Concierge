"""Inbound SMS through the paired-phone route, driven end to end.

Outbound device SMS was verified, but `/api/v1/device-sms/inbound` had no test:
the device token check, the exact-line check, duplicate suppression, the reply
queue and the inbound_verified_at write were all unproven. These drive the real
FastAPI route; only the database, tenant lookup and reply engine are substituted.
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import channel_authorization, device_sms, tenants

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "sms_enabled": True,
    "sms_transport": "device",
    "sms_from": "+6421555000",
}
DEVICE = {
    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "tenant_id": TENANT["id"],
    "from_number": "+6421555000",
    "enabled": True,
}
TOKEN = "x" * 60


class FakePool:
    def __init__(self, duplicate: bool = False):
        self.duplicate = duplicate
        self.verified = False
        self.inbound_rows = 0

    async def fetchrow(self, sql, *args):
        if "FROM sms_devices" in sql:
            expected = hashlib.sha256(TOKEN.encode()).hexdigest()
            if args and args[0] != expected:
                return None
            return dict(DEVICE)
        return None

    async def fetchval(self, sql, *args):
        if "INSERT INTO device_sms_inbound" in sql:
            if self.duplicate:
                return None
            self.inbound_rows += 1
            return args[1]
        return None

    async def execute(self, sql, *args):
        if "inbound_verified_at=now()" in sql:
            self.verified = True
        return "OK"


@pytest.fixture()
def app_client(monkeypatch):
    from app import main

    loop = None
    pool = FakePool()

    async def fetchrow(sql, *args):
        return await pool.fetchrow(sql, *args)

    async def fetchval(sql, *args):
        return await pool.fetchval(sql, *args)

    async def execute(sql, *args):
        return await pool.execute(sql, *args)

    fake = type("P", (), {})()
    fake.fetchrow, fake.fetchval, fake.execute = fetchrow, fetchval, execute
    monkeypatch.setattr(device_sms.db, "pool", lambda: fake)
    monkeypatch.setattr(tenants, "get_by_id", AsyncMock(return_value=dict(TENANT)))
    monkeypatch.setattr(channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "_sms_reply", AsyncMock(return_value="Sure, we can help."))
    enqueued: list[tuple] = []
    async def fake_enqueue(tenant, recipient, body, key, **kw):
        enqueued.append((recipient, body, key))
        return "queued"
    monkeypatch.setattr(device_sms, "enqueue", fake_enqueue)
    return TestClient(main.app), pool, enqueued


def _post(client, token=TOKEN, **body):
    payload = {"message_id": "m-1", "sender": "+6421000001", "to": "+6421555000",
               "body": "Do you do quotes?", **body}
    return client.post("/api/v1/device-sms/inbound", json=payload,
                       headers={"Authorization": "Bearer " + token})


def test_inbound_is_captured_and_replies(app_client):
    client, pool, enqueued = app_client
    response = _post(client)
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert pool.inbound_rows == 1
    assert pool.verified is True
    assert enqueued and enqueued[0][0] == "+6421000001"


def test_inbound_marks_the_device_receive_verified(app_client):
    client, pool, _ = app_client
    _post(client)
    assert pool.verified is True


def test_inbound_rejects_a_message_for_another_line(app_client):
    client, _, _ = app_client
    assert _post(client, to="+6421999999").status_code == 403


def test_inbound_rejects_a_message_from_the_device_itself(app_client):
    client, _, _ = app_client
    assert _post(client, sender="+6421555000").status_code == 403


def test_inbound_requires_a_device_token(app_client):
    client, _, _ = app_client
    assert _post(client, token="").status_code == 401
    assert _post(client, token="wrong" * 20).status_code == 401


def test_inbound_requires_sms_read_authorization(app_client, monkeypatch):
    client, _, _ = app_client
    monkeypatch.setattr(channel_authorization, "is_authorized", AsyncMock(return_value=False))
    assert _post(client).status_code == 403


def test_inbound_deduplicates_a_replayed_message(monkeypatch):
    from app import main

    pool = FakePool(duplicate=True)
    fake = type("P", (), {})()
    fake.fetchrow = pool.fetchrow
    fake.fetchval = pool.fetchval
    fake.execute = pool.execute
    monkeypatch.setattr(device_sms.db, "pool", lambda: fake)
    monkeypatch.setattr(tenants, "get_by_id", AsyncMock(return_value=dict(TENANT)))
    monkeypatch.setattr(channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "_sms_reply", AsyncMock(return_value="ignored"))
    client = TestClient(main.app)
    response = _post(client)
    assert response.status_code == 200 and response.json().get("duplicate") is True
    assert pool.inbound_rows == 0
