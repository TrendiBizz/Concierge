"""N7 WhatsApp / FB Messenger / IG DM inbound tests:
- Disabled cleanly by default (503 on webhooks, 409 on channel bind)
- When enabled, verifies hub challenge, validates X-Hub-Signature-256, and deduplicates WhatsApp/Messenger/IG messages
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import pathlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, owner_auth, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
    db._pool = pool
    return pool


def run(fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


@needs_db
def test_n7_meta_disabled_by_default_and_handles_whatsapp_messenger_ig(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_messaging_enabled", False, raising=False)

    async def _go(pool):
        t = await tenants.create("Meta Co", "https://metaco.example", "meta-co")
        inv = await owner_auth.make_invite(t["id"], "owner@metaco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Disabled by default
            ov = await client.get("/owner/meta-messaging", headers=headers)
            assert ov.status_code == 200 and ov.json()["platform_enabled"] is False
            assert (await client.get("/webhooks/meta/messaging?hub.mode=subscribe&hub.verify_token=x&hub.challenge=123")).status_code == 503
            assert (await client.post("/owner/meta-messaging/channels", headers=headers, json={
                "channel": "whatsapp", "external_id": "1001", "access_token": "sampletoken",
            })).status_code == 409

            # 2. Enable with test credentials
            monkeypatch.setattr(get_settings(), "meta_messaging_enabled", True, raising=False)
            monkeypatch.setattr(get_settings(), "meta_app_secret", "testsecret", raising=False)
            monkeypatch.setattr(get_settings(), "meta_webhook_verify_token", "verifytoken", raising=False)

            ch = await client.get("/webhooks/meta/messaging?hub.mode=subscribe&hub.verify_token=verifytoken&hub.challenge=CHAL99")
            assert ch.status_code == 200 and ch.text == "CHAL99"

            # Bind WhatsApp & Instagram channels
            for chan, ext_id in (("whatsapp", "WA-PHONE-1"), ("instagram", "IG-ACCT-1")):
                r = await client.post("/owner/meta-messaging/channels", headers=headers, json={
                    "channel": chan, "external_id": ext_id, "access_token": "sampletoken",
                })
                assert r.status_code == 201

            # Signed WhatsApp inbound webhook
            wa_payload = json.dumps({
                "object": "whatsapp_business_account",
                "entry": [{"changes": [{"value": {
                    "metadata": {"phone_number_id": "WA-PHONE-1"},
                    "contacts": [{"wa_id": "64211234567", "profile": {"name": "Aroha"}}],
                    "messages": [{"id": "wamid.1", "from": "64211234567", "text": {"body": "Kia ora, quote please"}}],
                }}]}],
            }).encode("utf-8")
            sig = "sha256=" + hmac.new(b"testsecret", wa_payload, hashlib.sha256).hexdigest()

            # Bad signature rejected
            assert (await client.post("/webhooks/meta/messaging", content=wa_payload, headers={"x-hub-signature-256": "sha256=bad"})).status_code == 401
            # Valid signature stored once (deduplicated on replay)
            ok1 = await client.post("/webhooks/meta/messaging", content=wa_payload, headers={"x-hub-signature-256": sig})
            ok2 = await client.post("/webhooks/meta/messaging", content=wa_payload, headers={"x-hub-signature-256": sig})
            assert ok1.status_code == 200 and ok1.json()["stored"] == 1
            assert ok2.status_code == 200 and ok2.json()["stored"] == 0

            ov2 = (await client.get("/owner/meta-messaging", headers=headers)).json()
            assert len(ov2["messages"]) == 1 and ov2["messages"][0]["sender_name"] == "Aroha"
    run(_go)
