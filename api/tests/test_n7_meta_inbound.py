"""N7 WhatsApp / FB Messenger / IG DM messaging tests:
- Disabled cleanly by default (503 on webhooks, 409 on channel bind)
- Webhook GET verification, X-Hub-Signature-256 HMAC validation, deduplication, and postbacks
- Social OAuth Meta finish persists encrypted Page/IG channels and strips tokens from HTTP response;
  disconnect unsubscribes Page webhooks and removes the channel
- WhatsApp Embedded Signup gated behind META_WA_EMBEDDED_SIGNUP_CONFIG_ID, subscribes WABA,
  stores encrypted token, routes inbound by phone_number_id, and unsubscribes on disconnect
- Outbound replies enforce Meta's 24-hour customer service window (and WhatsApp templates outside 24h)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import crypto_vault, db, meta_inbound, owner_auth, social_bridge, tenants
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

            # Postback event on Instagram
            ig_postback = json.dumps({
                "object": "instagram",
                "entry": [{"id": "IG-ACCT-1", "messaging": [{
                    "sender": {"id": "ig-user-9"},
                    "postback": {"mid": "igmid.pb1", "title": "Get a quote", "payload": "QUOTE"},
                }]}],
            }).encode("utf-8")
            ig_sig = "sha256=" + hmac.new(b"testsecret", ig_postback, hashlib.sha256).hexdigest()
            ok_ig = await client.post("/webhooks/meta/messaging", content=ig_postback, headers={"x-hub-signature-256": ig_sig})
            assert ok_ig.status_code == 200 and ok_ig.json()["stored"] == 1

            ov2 = (await client.get("/owner/meta-messaging", headers=headers)).json()
            assert len(ov2["messages"]) == 2
            assert any(m["sender_name"] == "Aroha" for m in ov2["messages"])
    run(_go)


@needs_db
def test_meta_social_oauth_sync_encrypts_tokens_and_unsubscribes_on_disconnect(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_messaging_enabled", True, raising=False)
    monkeypatch.setattr(get_settings(), "meta_app_secret", "testsecret", raising=False)
    monkeypatch.setattr(get_settings(), "meta_webhook_verify_token", "verifytoken", raising=False)

    graph_calls: list[tuple[str, str, str]] = []

    async def fake_graph(method: str, path: str, *, token: str = "", params=None, json_body=None, form_body=None):
        graph_calls.append((method, path, token))
        return 200, {"success": True}

    async def fake_finish_meta(user, network, state, code):
        return {
            "account_ids": ["acc_fb_1234567890123456"],
            "channels": [{
                "account_id": "acc_fb_1234567890123456",
                "channel": "messenger",
                "external_id": "998877665544",
                "page_id": "998877665544",
                "display_name": "Kiwi Plumbing Page",
                "access_token": "EAA_SECRET_PAGE_TOKEN",
                "webhook_subscribed": True,
            }],
        }

    async def fake_unlink_meta(user, network, account_id):
        return {"ok": True}

    monkeypatch.setattr(meta_inbound, "_graph_request", fake_graph)
    monkeypatch.setattr(social_bridge, "finish_meta_oauth", fake_finish_meta)
    monkeypatch.setattr(social_bridge, "unlink_meta", fake_unlink_meta)

    async def _go(pool):
        t = await tenants.create("Kiwi Plumbing", "https://kiwiplumbing.example", "kiwi-plumbing")
        inv = await owner_auth.make_invite(t["id"], "owner@kiwi.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/owner/social/oauth/meta/facebook/finish",
                headers=headers,
                json={"state": "s" * 40, "code": "oauth-code-123"},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["account_ids"] == ["acc_fb_1234567890123456"]
            # Access token must NEVER be returned to the browser
            assert "channels" not in body
            assert "EAA_SECRET_PAGE_TOKEN" not in json.dumps(body)

            row = await pool.fetchrow(
                "SELECT external_id, page_id, display_name, webhook_subscribed, access_token_enc "
                "FROM tenant_meta_channels WHERE tenant_id=$1 AND channel='messenger'",
                t["id"],
            )
            assert row is not None
            assert row["external_id"] == "998877665544"
            assert row["page_id"] == "998877665544"
            assert row["webhook_subscribed"] is True
            assert crypto_vault.is_encrypted(row["access_token_enc"])
            assert crypto_vault.decrypt_text(row["access_token_enc"], aad=f"meta:{t['id']}:messenger") == "EAA_SECRET_PAGE_TOKEN"

            # Disconnect unsubscribes Page webhook and removes the row
            del_res = await client.delete(
                "/owner/social/oauth/meta/facebook/accounts/acc_fb_1234567890123456",
                headers=headers,
            )
            assert del_res.status_code == 200
            assert ("DELETE", "998877665544/subscribed_apps", "EAA_SECRET_PAGE_TOKEN") in graph_calls
            left = await pool.fetchval("SELECT COUNT(*) FROM tenant_meta_channels WHERE tenant_id=$1", t["id"])
            assert left == 0
    run(_go)


@needs_db
def test_wa_embedded_signup_and_outbound_24h_window(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_messaging_enabled", True, raising=False)
    monkeypatch.setattr(get_settings(), "meta_app_secret", "testsecret", raising=False)
    monkeypatch.setattr(get_settings(), "meta_webhook_verify_token", "verifytoken", raising=False)
    monkeypatch.setattr(get_settings(), "meta_app_id", "", raising=False)
    monkeypatch.setattr(get_settings(), "meta_wa_embedded_signup_config_id", "", raising=False)
    monkeypatch.setattr(get_settings(), "public_base_url", "https://concierge.trendibizz.com", raising=False)

    graph_calls: list[tuple[str, str, dict | None]] = []

    async def fake_graph(method: str, path: str, *, token: str = "", params=None, json_body=None, form_body=None):
        graph_calls.append((method, path, json_body))
        if path == "oauth/access_token":
            return 200, {"access_token": "EAA_WA_SYSTEM_TOKEN"}
        if path == "112233445566/subscribed_apps" and method == "POST":
            return 200, {"success": True}
        if path == "112233445566/subscribed_apps" and method == "DELETE":
            return 200, {"success": True}
        if path == "778899001122":
            return 200, {"verified_name": "Trendi Test WA", "display_phone_number": "+64 21 000 0000"}
        if path == "778899001122/messages":
            return 200, {"messages": [{"id": f"wamid.out.{len(graph_calls)}"}]}
        if path == "112233445566/message_templates":
            return 200, {"data": [{"name": "appointment_reminder", "language": "en", "category": "UTILITY", "status": "APPROVED"}]}
        return 200, {"message_id": "m_out_1"}

    monkeypatch.setattr(meta_inbound, "_graph_request", fake_graph)

    async def _go(pool):
        t = await tenants.create("WA Co", "https://waco.example", "wa-co")
        inv = await owner_auth.make_invite(t["id"], "owner@waco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Disabled until META_WA_EMBEDDED_SIGNUP_CONFIG_ID and META_APP_ID are set
            start_off = await client.post("/owner/meta-messaging/whatsapp/embedded-signup/start", headers=headers)
            assert start_off.status_code == 409
            assert "META_WA_EMBEDDED_SIGNUP_CONFIG_ID" in start_off.json()["detail"]

            # 2. Enable Embedded Signup config
            monkeypatch.setattr(get_settings(), "meta_app_id", "123456789012345", raising=False)
            monkeypatch.setattr(get_settings(), "meta_wa_embedded_signup_config_id", "987654321098765", raising=False)

            start_ok = await client.post("/owner/meta-messaging/whatsapp/embedded-signup/start", headers=headers)
            assert start_ok.status_code == 200
            start_body = start_ok.json()
            assert "config_id=987654321098765" in start_body["authorization_url"]
            state = start_body["state"]

            # Complete Embedded Signup
            comp = await client.post(
                "/owner/meta-messaging/whatsapp/embedded-signup/complete",
                headers=headers,
                json={
                    "state": state,
                    "code": "wa-code-xyz",
                    "waba_id": "112233445566",
                    "phone_number_id": "778899001122",
                },
            )
            assert comp.status_code == 201
            comp_data = comp.json()
            assert comp_data["external_id"] == "778899001122"
            assert comp_data["waba_id"] == "112233445566"
            assert comp_data["webhook_subscribed"] is True
            assert ("POST", "112233445566/subscribed_apps", None) in graph_calls

            # Replaying the same state is rejected
            replay = await client.post(
                "/owner/meta-messaging/whatsapp/embedded-signup/complete",
                headers=headers,
                json={"state": state, "code": "wa-code-xyz", "waba_id": "112233445566", "phone_number_id": "778899001122"},
            )
            assert replay.status_code == 400

            # Inbound WhatsApp message routes by phone_number_id
            wa_in = json.dumps({
                "object": "whatsapp_business_account",
                "entry": [{"changes": [{"value": {
                    "metadata": {"phone_number_id": "778899001122"},
                    "contacts": [{"wa_id": "64219998888", "profile": {"name": "Tama"}}],
                    "messages": [{"id": "wamid.in.1", "from": "64219998888", "text": {"body": "Need a quote"}}],
                }}]}],
            }).encode("utf-8")
            sig = "sha256=" + hmac.new(b"testsecret", wa_in, hashlib.sha256).hexdigest()
            assert (await client.post("/webhooks/meta/messaging", content=wa_in, headers={"x-hub-signature-256": sig})).json()["stored"] == 1

            # Conversations list shows window_open = True
            convs = (await client.get("/owner/meta-messaging/conversations", headers=headers)).json()["conversations"]
            assert len(convs) == 1 and convs[0]["window_open"] is True

            # Reply inside 24h window succeeds
            rep = await client.post(
                "/owner/meta-messaging/conversations/whatsapp/64219998888/reply",
                headers=headers,
                json={"text": "Sure Tama, what suburb are you in?"},
            )
            assert rep.status_code == 200 and rep.json()["direction"] == "out"
            assert any(
                m == "POST" and p == "778899001122/messages" and b and b.get("type") == "text"
                for m, p, b in graph_calls
            )

            # Templates endpoint returns approved templates
            tpls = (await client.get("/owner/meta-messaging/whatsapp/templates", headers=headers)).json()["templates"]
            assert len(tpls) == 1 and tpls[0]["name"] == "appointment_reminder"

            # Backdate inbound message > 24h ago: free-text reply blocked (409), template allowed (200)
            old_ts = datetime.now(timezone.utc) - timedelta(hours=25)
            await pool.execute(
                "UPDATE meta_inbound_messages SET created_at=$1 WHERE external_message_id='wamid.in.1'",
                old_ts,
            )
            blocked = await client.post(
                "/owner/meta-messaging/conversations/whatsapp/64219998888/reply",
                headers=headers,
                json={"text": "Checking in"},
            )
            assert blocked.status_code == 409

            tpl_rep = await client.post(
                "/owner/meta-messaging/conversations/whatsapp/64219998888/reply",
                headers=headers,
                json={"template_name": "appointment_reminder", "template_language": "en"},
            )
            assert tpl_rep.status_code == 200
            assert any(
                m == "POST" and p == "778899001122/messages" and b and b.get("type") == "template"
                for m, p, b in graph_calls
            )

            # Deleting channel unsubscribes WABA
            del_ch = await client.delete(f"/owner/meta-messaging/channels/{comp_data['id']}", headers=headers)
            assert del_ch.status_code == 200
            assert ("DELETE", "112233445566/subscribed_apps", None) in graph_calls
    run(_go)
