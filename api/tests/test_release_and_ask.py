"""Version 1, the "what's new" notice, the release email, the 7am toggle and the read-only Ask box.

One event loop with httpx's ASGITransport (see test_crm_owner_tools.py for why).
"""
import asyncio
import os
import pathlib
import uuid

import asyncpg
import httpx
import pytest

from app import db, owner_auth, owner_ask, owner_onboarding, releases

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


def test_the_current_release_is_version_1():
    assert releases.CURRENT_VERSION == 1 and releases.label() == "Version 1"
    assert releases.notice(0)["unseen"] and not releases.notice(1)["unseen"]
    assert releases.notice(0)["label"] == "Version 1" and releases.notice(0)["notes"]


async def _pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _tenant(slug="acme", email="boss@acme.test"):
    return await db.pool().fetchval(
        "INSERT INTO tenants (slug, name, public_key, notify_email) VALUES ($1,$2,$3,$4) RETURNING id",
        slug, slug.title(), "pk" + uuid.uuid4().hex[:6], email)


async def _user(tenant):
    return await db.pool().fetchrow(
        "INSERT INTO tenant_users (tenant_id,email,role,password_hash) VALUES ($1,'o@acme.test','owner','x') "
        "RETURNING id, tenant_id, email, role", tenant)


def _client(user):
    from app import main as app_main
    u = {"id": user["id"], "tenant_id": user["tenant_id"], "email": user["email"], "role": "owner",
         "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: u
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://test")


def _reset():
    from app import main as app_main
    app_main.app.dependency_overrides.clear()
    db._pool = None


@needs_db
def test_notice_shows_until_dismissed_then_stays_dismissed():
    async def run():
        pool = await _pool()
        try:
            user = await _user(await _tenant())
            async with _client(user) as c:
                first = (await c.get("/owner/release")).json()
                assert first["unseen"] and first["label"] == "Version 1"
                assert (await c.post("/owner/release/seen")).status_code == 200
                assert (await c.get("/owner/release")).json()["unseen"] is False
                public = (await c.get("/version")).json()
                assert public == {"version": 1, "label": "Version 1"}
                assert (await c.get("/owner/version")).json() == public  # the path the public edge actually forwards
        finally:
            _reset(); await pool.close()
    asyncio.run(run())


@needs_db
def test_release_email_previews_by_default_and_never_sends_twice():
    async def run():
        pool = await _pool()
        try:
            tid = await _tenant()
            dry = await releases.announce(1)
            assert dry["dry_run"] and dry["queued"] == 0 and dry["recipients"][0]["to"] == "boss@acme.test"
            assert await pool.fetchval("SELECT count(*) FROM outbox") == 0
            assert (await releases.announce(1, dry_run=False))["queued"] == 1
            assert (await releases.announce(1, dry_run=False))["queued"] == 0
            row = await pool.fetchrow("SELECT subject, body FROM outbox WHERE tenant_id=$1", tid)
            assert "Version 1" in row["subject"] and "Nothing about your customers" in row["body"]
        finally:
            _reset(); await pool.close()
    asyncio.run(run())


@needs_db
def test_daily_summary_can_be_switched_on_and_off_by_the_owner():
    async def run():
        pool = await _pool()
        try:
            await _tenant()
            await owner_onboarding.update_profile("acme", owner_onboarding.OwnerBusinessProfile(daily_summary=True))
            assert await pool.fetchval("SELECT daily_summary FROM tenants WHERE slug='acme'") is True
            await owner_onboarding.update_profile("acme", owner_onboarding.OwnerBusinessProfile(daily_summary=False))
            assert await pool.fetchval("SELECT daily_summary FROM tenants WHERE slug='acme'") is False
        finally:
            _reset(); await pool.close()
    asyncio.run(run())


@needs_db
def test_ask_answers_from_the_brief_with_no_tools(monkeypatch):
    seen = {}

    class Reply:
        content = "We open at 8."

    async def fake(messages, tools=None, **kw):
        seen["system"] = messages[0]["content"]; seen["tools"] = tools
        return Reply()

    monkeypatch.setattr(owner_ask.llm, "complete", fake)

    async def run():
        pool = await _pool()
        try:
            tid = await _tenant()
            await pool.execute(
                "INSERT INTO chunks (tenant_id,url,title,content,embedding) VALUES ($1,$2,'Hours','Open 8am to 5pm weekdays',"
                "array_fill(0::float4, ARRAY[1536])::vector)", tid, "manual:owner:abc")
            user = await _user(tid)
            async with _client(user) as c:
                out = await c.post("/owner/ask", json={"question": "When do we open?"})
                assert out.json() == {"answer": "We open at 8."}
                assert (await c.post("/owner/ask", json={"question": ""})).status_code == 422
        finally:
            _reset(); await pool.close()
    asyncio.run(run())
    assert "Open 8am to 5pm weekdays" in seen["system"] and "Figures right now" in seen["system"]
    assert seen["tools"] is None
