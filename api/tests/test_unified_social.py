"""End-to-end tests for the unified Concierge social module, token refresh, dry-run publish,
legacy SQLite + Rust vault migration, and dual-app Meta WhatsApp messaging.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import sys
import time
from urllib.parse import parse_qs, urlsplit

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
except ImportError:
    _AESGCM = None

from app import crypto_vault, db, meta_inbound, owner_auth, social, tenants
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


def _configure_all_providers(monkeypatch):
    s = get_settings()
    cb = "https://concierge.trendibizz.com/owner/social/oauth/callback"
    monkeypatch.setattr(s, "social_service_enabled", True, raising=False)
    monkeypatch.setattr(s, "social_live_publishing", False, raising=False)
    monkeypatch.setattr(s, "social_facebook_client_id", "fb-app-123", raising=False)
    monkeypatch.setattr(s, "social_facebook_client_secret", "fb-sec-123", raising=False)
    monkeypatch.setattr(s, "social_facebook_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_instagram_login_mode", "facebook", raising=False)
    monkeypatch.setattr(s, "social_linkedin_client_id", "li-id-123", raising=False)
    monkeypatch.setattr(s, "social_linkedin_client_secret", "li-sec-123", raising=False)
    monkeypatch.setattr(s, "social_linkedin_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_linkedin_organization_client_id", "lio-id-123", raising=False)
    monkeypatch.setattr(s, "social_linkedin_organization_client_secret", "lio-sec-123", raising=False)
    monkeypatch.setattr(s, "social_linkedin_organization_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_x_client_id", "x-id-123", raising=False)
    monkeypatch.setattr(s, "social_x_client_secret", "x-sec-123", raising=False)
    monkeypatch.setattr(s, "social_x_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_tiktok_client_key", "tt-key-123", raising=False)
    monkeypatch.setattr(s, "social_tiktok_client_secret", "tt-sec-123", raising=False)
    monkeypatch.setattr(s, "social_tiktok_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_google_client_id", "g-id-123", raising=False)
    monkeypatch.setattr(s, "social_google_client_secret", "g-sec-123", raising=False)
    monkeypatch.setattr(s, "social_google_callback", cb, raising=False)
    monkeypatch.setattr(s, "meta_graph_version", "v22.0", raising=False)


@needs_db
def test_unified_social_oauth_urls_token_refresh_and_dry_run_all_seven_networks(monkeypatch):
    _configure_all_providers(monkeypatch)

    async def _go(pool):
        t = await tenants.create("Unified Co", "https://unified.example", "unified-co")
        inv = await owner_auth.make_invite(t["id"], "owner@unified.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Status lists all 7 configured providers
            st = await client.get("/owner/social/status", headers=headers)
            assert st.status_code == 200
            body = st.json()
            assert body["enabled"] is True
            assert body["callback_path"] == "/owner/social/oauth/callback"
            for net in ("facebook", "instagram", "linkedin", "linkedin_organization", "x", "tiktok", "google_business"):
                assert body["providers"][net] is True

            # 2. Every network builds a valid OAuth URL with the exact callback
            routes = [
                ("/owner/social/oauth/meta/facebook/start", "www.facebook.com"),
                ("/owner/social/oauth/meta/instagram/start", "www.facebook.com"),
                ("/owner/social/oauth/linkedin/start", "www.linkedin.com"),
                ("/owner/social/oauth/linkedin_organization/start", "www.linkedin.com"),
                ("/owner/social/oauth/x/start", "x.com"),
                ("/owner/social/oauth/tiktok/start", "www.tiktok.com"),
                ("/owner/social/oauth/google/start", "accounts.google.com"),
            ]
            for route, expected_host in routes:
                r = await client.post(route, headers=headers)
                assert r.status_code == 200, f"{route}: {r.text}"
                data = r.json()
                parsed = urlsplit(data["authorization_url"])
                assert parsed.scheme == "https"
                assert parsed.hostname == expected_host
                qs = parse_qs(parsed.query)
                assert qs["redirect_uri"] == ["https://concierge.trendibizz.com/owner/social/oauth/callback"]
                assert qs["state"] == [data["state"]]
                assert len(data["state"]) >= 32

            # 3. Seed accounts for all 7 networks and verify dry-run publish without outbound HTTP
            acct_ids: dict[str, str] = {}
            for net, ext in (
                ("facebook", "page-123"),
                ("instagram", "ig-456"),
                ("linkedin", "urn:li:person:abc"),
                ("linkedin_organization", "urn:li:organization:999"),
                ("x", "x-789"),
                ("tiktok", "tt-open-1"),
                ("google_business", "accounts/1/locations/2"),
            ):
                aid = await social.store.upsert_verified_account(
                    customer_slug="unified-co",
                    network=net,
                    external_id=ext,
                    display_name=f"Unified {net}",
                    access_token=f"tok-{net}",
                    refresh_token=f"ref-{net}",
                    expires_at=int(time.time()) + 120,
                    granted_scopes="w_member_social user.info.basic",
                )
                acct_ids[net] = aid

            # Create a draft across text-capable networks and run dry-run
            draft = await client.post(
                "/owner/social/posts",
                headers=headers,
                json={
                    "content": "Spring specials are live in Auckland!",
                    "account_ids": [acct_ids["facebook"], acct_ids["linkedin"], acct_ids["x"], acct_ids["google_business"]],
                    "link": "https://unified.example/spring",
                    "hashtags": "#auckland #spring",
                },
            )
            assert draft.status_code == 200, draft.text
            pid = draft.json()["id"]

            dr = await client.post(f"/owner/social/posts/{pid}/dry-run", headers=headers)
            assert dr.status_code == 200, dr.text
            dr_body = dr.json()
            assert dr_body["dry_run"] is True
            assert len(dr_body["results"]) == 4
            assert all(item["ok"] is True and item["payload"]["url"].startswith("https://") for item in dr_body["results"])

            # Verify Instagram + TikTok dry-run with HTTPS media
            media_draft = await client.post(
                "/owner/social/posts",
                headers=headers,
                json={
                    "content": "Watch our latest build!",
                    "account_ids": [acct_ids["instagram"], acct_ids["tiktok"], acct_ids["linkedin_organization"]],
                    "media": ["https://unified.example/clip.mp4"],
                },
            )
            assert media_draft.status_code == 200
            dr2 = await client.post(f"/owner/social/posts/{media_draft.json()['id']}/dry-run", headers=headers)
            assert dr2.status_code == 200
            assert all(item["ok"] is True for item in dr2.json()["results"])

            # 4. Token refresh path (mock provider token endpoint)
            async def fake_http(method, url, **kwargs):
                assert "api.x.com/2/oauth2/token" in url
                return 200, {
                    "access_token": "new-x-access-token",
                    "refresh_token": "new-x-refresh-token",
                    "expires_in": 7200,
                }

            monkeypatch.setattr(social.oauth, "_http_json", fake_http)
            ren = await client.post(f"/owner/social/oauth/renew/{acct_ids['x']}", headers=headers)
            assert ren.status_code == 200, ren.text
            assert ren.json()["ok"] is True
            creds = await social.store.get_account_credentials("unified-co", acct_ids["x"])
            assert creds["access_token"] == "new-x-access-token"
            assert creds["refresh_token"] == "new-x-refresh-token"

            # 5. Owner approval workflow required before scheduling
            sub = await client.post(f"/owner/social/posts/{pid}/submit", headers=headers)
            assert sub.status_code == 200 and sub.json()["status"] == "pending_approval"
            req = await client.post(
                f"/owner/social/posts/{pid}/approval-request",
                headers=headers,
                json={"scheduled_at": int(time.time()) + 3600},
            )
            assert req.status_code == 200
            tok = req.json()["token"]
            app_res = await client.post(f"/owner/social/approvals/{tok}/approve", headers=headers)
            assert app_res.status_code == 200 and app_res.json()["status"] == "scheduled"
            # Single-use approval token cannot be replayed
            replay = await client.post(f"/owner/social/approvals/{tok}/approve", headers=headers)
            assert replay.status_code == 404

    run(_go)


@needs_db
def test_legacy_sqlite_vault_migration_reencrypts_with_concierge_n9_vault(tmp_path, monkeypatch):
    scripts_vps = str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps")
    if scripts_vps not in sys.path:
        sys.path.insert(0, scripts_vps)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migrate_social_db", pathlib.Path(scripts_vps) / "migrate-social-db.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Create a legacy SQLite DB matching Rust social-service schema + AES-256-GCM sealed tokens
    raw_key = os.urandom(32)
    key_b64 = base64.b64encode(raw_key).decode("ascii")

    if _AESGCM is not None:
        def seal_rust(plain: str, label: str) -> str:
            nonce = os.urandom(12)
            ct = _AESGCM(raw_key).encrypt(nonce, plain.encode("utf-8"), label.encode("utf-8"))
            return base64.b64encode(nonce + ct).decode("ascii")
    else:
        def seal_rust(plain: str, label: str) -> str:
            return base64.b64encode(f"{label}::{plain}".encode("utf-8")).decode("ascii")

        def fake_open(k, sealed, label):
            decoded = base64.b64decode(sealed).decode("utf-8")
            prefix = f"{label}::"
            assert decoded.startswith(prefix)
            return decoded[len(prefix):]

        monkeypatch.setattr(mod, "open_legacy_vault", fake_open)

    db_file = tmp_path / "legacy-social.db"
    sc = sqlite3.connect(str(db_file))
    sc.executescript("""
        CREATE TABLE customers(id TEXT PRIMARY KEY, name TEXT NOT NULL, rules TEXT NOT NULL,
            approval_contact TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE accounts(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, network TEXT NOT NULL,
            external_id TEXT NOT NULL, display_name TEXT NOT NULL, token_enc TEXT NOT NULL,
            refresh_enc TEXT, needs_reauth INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE account_consents(account_id TEXT PRIMARY KEY, granted_scopes TEXT NOT NULL,
            authorized_at INTEGER NOT NULL, disconnected_at INTEGER);
        CREATE TABLE account_expiries(account_id TEXT PRIMARY KEY, expires_at INTEGER);
        CREATE TABLE posts(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT NOT NULL, scheduled_at INTEGER, revision INTEGER NOT NULL, approved_revision INTEGER);
        CREATE TABLE approvals(token_hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL, post_id TEXT NOT NULL,
            revision INTEGER NOT NULL, scheduled_at INTEGER, expires_at INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE post_results(post_id TEXT NOT NULL, account_id TEXT NOT NULL, external_post_id TEXT,
            error TEXT, at INTEGER NOT NULL, ok INTEGER NOT NULL, PRIMARY KEY(post_id, account_id, ok));
        CREATE TABLE events(at INTEGER NOT NULL, customer_id TEXT NOT NULL, post_id TEXT, kind TEXT NOT NULL, detail TEXT NOT NULL);
    """)
    now = int(time.time())
    sc.execute("INSERT INTO customers VALUES('pukeko-construction', 'Pukeko Construction', '{}', '', ?)", (now,))
    lbl = "pukeko-construction|linkedin|urn:li:person:conrad"
    sc.execute(
        "INSERT INTO accounts VALUES('acct_legacy_1234567890', 'pukeko-construction', 'linkedin', 'urn:li:person:conrad', 'Conrad', ?, ?, 0)",
        (seal_rust("secret-access-tok", lbl), seal_rust("secret-refresh-tok", lbl)),
    )
    sc.execute("INSERT INTO account_consents VALUES('acct_legacy_1234567890', 'openid profile w_member_social', ?, NULL)", (now,))
    sc.execute("INSERT INTO account_expiries VALUES('acct_legacy_1234567890', ?)", (now + 86400,))
    sc.execute(
        "INSERT INTO posts VALUES('post_legacy_1234567890', 'pukeko-construction', ?, 'published', ?, 1, 1)",
        (json.dumps({"content": "Migrated post", "account_ids": ["acct_legacy_1234567890"], "media": []}), now),
    )
    sc.execute("INSERT INTO post_results VALUES('post_legacy_1234567890', 'acct_legacy_1234567890', 'ext-1', NULL, ?, 1)", (now,))
    sc.commit()
    sc.close()

    async def _go(pool):
        counts = await mod.migrate_sqlite_to_postgres(str(db_file), key_b64)
        assert counts["customers"] == 1
        assert counts["accounts"] == 1
        assert counts["accounts_reencrypted"] == 1
        assert counts["posts"] == 1
        assert counts["post_results"] == 1

        # Verify token was re-encrypted with Concierge's N9 crypto_vault (enc:v1:aesgcm:) and decrypts cleanly
        raw_enc = await pool.fetchval("SELECT token_enc FROM social_accounts WHERE id='acct_legacy_1234567890'")
        assert crypto_vault.is_encrypted(raw_enc)
        creds = await social.store.get_account_credentials("pukeko-construction", "acct_legacy_1234567890")
        assert creds["access_token"] == "secret-access-tok"
        assert creds["refresh_token"] == "secret-refresh-tok"

        # Verify idempotency on second run
        counts2 = await mod.migrate_sqlite_to_postgres(str(db_file), key_b64)
        assert counts2["accounts"] == 1

    run(_go)


@needs_db
def test_dual_meta_app_whatsapp_credentials_and_webhook_signature(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "meta_messaging_enabled", True, raising=False)
    monkeypatch.setattr(s, "meta_app_id", "111111111111111", raising=False)
    monkeypatch.setattr(s, "meta_app_secret", "main-app-secret", raising=False)
    monkeypatch.setattr(s, "meta_webhook_verify_token", "verify-tok", raising=False)
    monkeypatch.setattr(s, "meta_wa_app_id", "29227891546892110", raising=False)
    monkeypatch.setattr(s, "meta_wa_app_secret", "", raising=False)
    monkeypatch.setattr(s, "meta_wa_embedded_signup_config_id", "", raising=False)

    # Embedded signup MUST stay off until META_WA_APP_SECRET and META_WA_EMBEDDED_SIGNUP_CONFIG_ID are set
    info_off = meta_inbound.wa_embedded_signup_info()
    assert info_off["enabled"] is False
    assert "META_WA_APP_SECRET" in info_off["unavailable_reason"]
    assert "META_WA_EMBEDDED_SIGNUP_CONFIG_ID" in info_off["unavailable_reason"]

    # Now set the WA app secret + config ID
    monkeypatch.setattr(s, "meta_wa_app_secret", "wa-app-secret", raising=False)
    monkeypatch.setattr(s, "meta_wa_embedded_signup_config_id", "cfg-wa-999", raising=False)
    info_on = meta_inbound.wa_embedded_signup_info()
    assert info_on["enabled"] is True

    async def _go(pool):
        t = await tenants.create("DualApp Co", "https://dual.example", "dual-co")
        inv = await owner_auth.make_invite(t["id"], "owner@dual.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Start WhatsApp Embedded Signup uses the dedicated Trendi Messaging app ID
            start = await client.post("/owner/meta-messaging/whatsapp/embedded-signup/start", headers=headers)
            assert start.status_code == 200
            qs = parse_qs(urlsplit(start.json()["authorization_url"]).query)
            assert qs["client_id"] == ["29227891546892110"]
            assert qs["config_id"] == ["cfg-wa-999"]

            # Webhook accepts signatures from EITHER the main app secret OR the WhatsApp app secret
            payload = json.dumps({"object": "page", "entry": []}).encode("utf-8")
            sig_main = "sha256=" + hmac.new(b"main-app-secret", payload, hashlib.sha256).hexdigest()
            sig_wa = "sha256=" + hmac.new(b"wa-app-secret", payload, hashlib.sha256).hexdigest()
            sig_bad = "sha256=" + hmac.new(b"wrong-secret", payload, hashlib.sha256).hexdigest()

            assert (await client.post("/webhooks/meta/messaging", content=payload, headers={"x-hub-signature-256": sig_main})).status_code == 200
            assert (await client.post("/webhooks/meta/messaging", content=payload, headers={"x-hub-signature-256": sig_wa})).status_code == 200
            assert (await client.post("/webhooks/meta/messaging", content=payload, headers={"x-hub-signature-256": sig_bad})).status_code == 401

    run(_go)
