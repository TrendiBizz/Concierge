"""N6: API keys, complete webhooks with retry, and the (disabled-by-default) connectors."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib

import asyncpg
import httpx
import pytest

from app import api_keys, db, integrations, main as app_main, owner_auth, portability
from app.config import get_settings

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
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


async def _tenant(pool, slug):
    return await pool.fetchval(
        "INSERT INTO tenants(slug,name,public_key) VALUES($1,$2,$3) RETURNING id", slug, slug.title(), "pk_" + slug)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://t")


@needs_db
def test_api_key_is_hashed_scoped_to_its_tenant_and_revocable():
    async def go(pool):
        a, b = await _tenant(pool, "a"), await _tenant(pool, "b")
        await pool.execute("INSERT INTO leads(tenant_id,name,message,channel,source_key) VALUES($1,'Ann','hi','chat','k1')", a)
        await pool.execute("INSERT INTO leads(tenant_id,name,message,channel,source_key) VALUES($1,'Bob','yo','chat','k2')", b)
        made = await api_keys.create_key(a, "zap")
        stored = await pool.fetchval("SELECT key_hash FROM tenant_api_keys")
        assert made["key"] not in stored and made["key"].startswith("cnc_")
        async with _client() as c:
            h = {"Authorization": "Bearer " + made["key"]}
            r = await c.get("/api/v1/enquiries", headers=h)
            assert r.status_code == 200
            assert [e["name"] for e in r.json()["enquiries"]] == ["Ann"]  # never Bob
            assert (await c.get("/api/v1/enquiries")).status_code == 401
            assert (await c.get("/api/v1/enquiries", headers={"Authorization": "Bearer cnc_nope"})).status_code == 401
            assert await api_keys.revoke_key(b, made["id"]) is False  # another tenant cannot revoke it
            assert await api_keys.revoke_key(a, made["id"]) is True
            assert (await c.get("/api/v1/enquiries", headers=h)).status_code == 401
    run(go)


@needs_db
def test_new_events_are_queued_and_failed_delivery_backs_off_then_recovers(monkeypatch):
    async def go(pool):
        t = await _tenant(pool, "hook")
        await pool.execute("INSERT INTO tenant_webhooks(tenant_id,url,secret) VALUES($1,'https://x.example/h','s'*16)".replace("'s'*16", "'ssssssssssssssss'"), t)
        for ev in ("customer.enquiry", "quote.accepted", "appointment.booked", "call.completed"):
            assert ev in portability.EVENTS
        calls = []

        async def fake_post(url, **kw):
            calls.append(kw["headers"]["X-Concierge-Event"])
            return httpx.Response(500 if len(calls) == 1 else 200)
        monkeypatch.setattr(portability.public_fetch, "post_public", fake_post)
        monkeypatch.setattr(portability.asyncio, "create_task", lambda c: c.close())
        await portability.emit(t, "call.completed", {"call_sid": "CA1"})
        assert (await portability.deliver_pending(t))["failed"] == 1
        row = await pool.fetchrow("SELECT attempts,next_attempt_at > now() AS later FROM webhook_events")
        assert row["attempts"] == 1 and row["later"]
        assert (await portability.retry_all()) == 0  # not due yet
        await pool.execute("UPDATE webhook_events SET next_attempt_at=now()")
        assert (await portability.retry_all()) == 1  # background sweep delivers it
        assert await pool.fetchval("SELECT delivered_at IS NOT NULL FROM webhook_events")
    run(go)


@needs_db
def test_phone_finish_and_enquiry_emit_events(monkeypatch):
    async def go(pool):
        from app import phone_relay
        t = await _tenant(pool, "ph")
        await pool.execute("INSERT INTO phone_calls(call_sid,tenant_id,from_number,to_number) VALUES('CA'||repeat('1',32),$1,'+64211','+649')", t)
        seen = []

        async def spy(tid, ev, payload):
            seen.append(ev)
        monkeypatch.setattr(portability, "emit", spy)
        await phone_relay.finish("CA" + "1" * 32, "completed")
        assert seen == ["call.completed"]
    run(go)


def test_connectors_are_disabled_without_credentials():
    info = integrations.available()
    for p in ("xero", "m365", "tradify", "fergus"):
        assert info[p]["enabled"] is False and info[p]["unavailable_reason"]
    assert info["servicem8"]["enabled"] is True  # customer brings their own key
    with pytest.raises(Exception) as e:
        integrations._require("xero")
    assert getattr(e.value, "status_code", None) == 409


def test_oauth_state_is_signed_expiring_and_provider_bound(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ADMIN_TOKEN", "test-oauth-signing-secret")
    get_settings.cache_clear()
    try:
        s = integrations.make_state("t-1", "xero")
        assert integrations.read_state(s, "xero") == "t-1"
        with pytest.raises(Exception):
            integrations.read_state(s, "m365")
        with pytest.raises(Exception):
            integrations.read_state(s[:-2] + "00", "xero")
        with pytest.raises(Exception):
            integrations.read_state(integrations.make_state("t-1", "xero", ttl=-5), "xero")
    finally:
        get_settings.cache_clear()


@needs_db
def test_xero_pushes_contact_once_and_refreshes_expired_token(monkeypatch):
    async def go(pool):
        t = await _tenant(pool, "x")
        monkeypatch.setattr(get_settings(), "xero_client_id", "id", raising=False)
        monkeypatch.setattr(get_settings(), "xero_client_secret", "sec", raising=False)
        await integrations._save(t, "xero", {"access_token": "old", "refresh_token": "r", "expires_at": 1,
                                             "xero_tenant_id": "xt"})
        sent = []

        async def fake(method, url, **kw):
            sent.append((method, url))
            if "token" in url:
                return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 1800})
            return httpx.Response(200, json={"Contacts": [{"ContactID": "C1"}]})
        monkeypatch.setattr(integrations, "http", fake)
        payload = {"case_key": "k1", "name": "Ann", "email": "a@x.nz"}
        await integrations.dispatch(t, "customer.created", payload)
        await integrations.dispatch(t, "customer.enquiry", payload)  # idempotent
        assert [u for _, u in sent if "Contacts" in u] == ["https://api.xero.com/api.xro/2.0/Contacts"]
        assert any("token" in u for _, u in sent)
        assert await pool.fetchval("SELECT external_id FROM integration_links") == "C1"
        assert integrations._creds(await integrations._row(t, "xero"))["access_token"] == "new"
    run(go)


@needs_db
def test_servicem8_creates_client_and_job_and_failure_is_recorded_not_raised(monkeypatch):
    async def go(pool):
        t = await _tenant(pool, "sm")
        await integrations._save(t, "servicem8", {"api_key": "k" * 12})
        calls = []

        async def fake(method, url, **kw):
            calls.append(url)
            return httpx.Response(200, headers={"x-record-uuid": "U" + str(len(calls))}, json={})
        monkeypatch.setattr(integrations, "http", fake)
        p = {"lead_id": "L1", "case_key": "k1", "name": "Ann", "message": "leak", "channel": "phone"}
        await integrations.dispatch(t, "customer.enquiry", p)
        assert [u.rsplit("/", 1)[1] for u in calls] == ["company.json", "job.json"]

        async def boom(method, url, **kw):
            return httpx.Response(500)
        monkeypatch.setattr(integrations, "http", boom)
        await integrations.dispatch(t, "customer.enquiry", {**p, "lead_id": "L2"})
        assert "HTTP 500" in await pool.fetchval("SELECT last_error FROM tenant_integrations")
    run(go)


@needs_db
def test_owner_listing_never_exposes_credentials():
    async def go(pool):
        t = await _tenant(pool, "ls")
        await integrations._save(t, "servicem8", {"api_key": "supersecretkey"})
        app_main.app.dependency_overrides[owner_auth.current_user] = lambda: {
            "tenant_id": t, "role": "owner", "id": None, "email": "o@x.nz"}
        try:
            async with _client() as c:
                r = await c.get("/owner/integrations")
            assert r.status_code == 200 and "supersecretkey" not in r.text
            assert {i["provider"] for i in r.json()["integrations"]} == set(integrations.PROVIDERS)
        finally:
            app_main.app.dependency_overrides.clear()
    run(go)
