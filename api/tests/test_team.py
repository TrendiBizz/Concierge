"""Who can get in, and taking it away again.

The gap this closes: a business could invite staff but never revoke them, so a departed employee
kept their login.

Everything runs inside ONE event loop. A FastAPI TestClient runs the app in its own thread and
loop, so an asyncpg pool created by asyncio.run() in the test is bound to a dead loop and the
request hangs forever -- this suite hung for ten minutes before that was obvious. httpx's
ASGITransport drives the same app object in the current loop instead.
"""
import os
import pathlib
import uuid

import asyncpg
import httpx
import pytest

from app import db, owner_auth

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _seed():
    """A tenant with one owner, one editor and one viewer."""
    pool = db.pool()
    tenant = await pool.fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
        "acme", "Acme", "pk_" + uuid.uuid4().hex[:8])
    people = {}
    for email, role in (("owner@acme.test", "owner"), ("editor@acme.test", "editor"),
                        ("gone@acme.test", "viewer")):
        people[role] = await pool.fetchval(
            "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
            "VALUES ($1,$2,$3,'x') RETURNING id", tenant, email, role)
    return tenant, people


def _client_as(tenant, user_id, role="owner"):
    from app import main as app_main
    user = {"id": str(user_id), "tenant_id": tenant, "email": str(user_id), "role": role,
            "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app),
                             base_url="http://test")


def _reset(app_main):
    app_main.app.dependency_overrides.clear()
    db._pool = None


def test_the_team_list_shows_everyone_and_who_you_are():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            async with _client_as(tenant, people["owner"]) as client:
                response = await client.get("/owner/team")
                assert response.status_code == 200, response.text
                body = response.json()
                assert {m["email"] for m in body["members"]} == {
                    "owner@acme.test", "editor@acme.test", "gone@acme.test"}
                assert body["you"] == str(people["owner"])
                assert body["invitations"] == []
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())


def test_a_role_can_be_changed():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            async with _client_as(tenant, people["owner"]) as client:
                response = await client.patch(f"/owner/team/{people['viewer']}", json={"role": "editor"})
                assert response.status_code == 200, response.text
            row = await db.pool().fetchrow("SELECT role FROM tenant_users WHERE id=$1", people["viewer"])
            assert row["role"] == "editor"
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())


def test_the_last_owner_cannot_be_removed_or_demoted():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            async with _client_as(tenant, people["owner"]) as client:
                demote = await client.patch(f"/owner/team/{people['owner']}", json={"role": "editor"})
                assert demote.status_code == 400
                assert "at least one owner" in demote.json()["detail"]
                remove_self = await client.post(f"/owner/team/{people['owner']}/deactivate")
                assert remove_self.status_code == 400
                assert "your own access" in remove_self.json()["detail"]
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())


def test_deactivating_someone_ends_their_access_immediately():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            session_id = await db.pool().fetchval(
                "INSERT INTO tenant_sessions (user_id, token_hash, expires_at) "
                "VALUES ($1, $2, now() + interval '30 days') RETURNING id",
                people["viewer"], "hash-" + uuid.uuid4().hex)
            async with _client_as(tenant, people["owner"]) as client:
                response = await client.post(f"/owner/team/{people['viewer']}/deactivate")
                assert response.status_code == 200, response.text
                assert response.json()["active"] is False

                row = await db.pool().fetchrow("SELECT active FROM tenant_users WHERE id=$1", people["viewer"])
                assert row["active"] is False, "the account stayed active"
                left = await db.pool().fetchval("SELECT count(*) FROM tenant_sessions WHERE id=$1", session_id)
                assert left == 0, "an existing session survived deactivation"

                again = await client.post(f"/owner/team/{people['viewer']}/reactivate")
                assert again.status_code == 200 and again.json()["active"] is True
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())


def test_only_an_owner_can_change_the_team():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            async with _client_as(tenant, people["editor"], role="editor") as client:
                assert (await client.get("/owner/team")).status_code == 200
                blocked = await client.patch(f"/owner/team/{people['viewer']}", json={"role": "owner"})
                assert blocked.status_code == 403, "an editor promoted someone to owner"
                assert (await client.post(f"/owner/team/{people['viewer']}/deactivate")).status_code == 403
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())


def test_a_person_from_another_business_cannot_be_touched():
    async def run():
        from app import main as app_main
        pool = await _pool()
        try:
            tenant, people = await _seed()
            other = await db.pool().fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
                "other", "Other", "pk_" + uuid.uuid4().hex[:8])
            stranger = await db.pool().fetchval(
                "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
                "VALUES ($1,'x@other.test','editor','x') RETURNING id", other)
            async with _client_as(tenant, people["owner"]) as client:
                assert (await client.patch(f"/owner/team/{stranger}", json={"role": "viewer"})).status_code == 404
                assert (await client.post(f"/owner/team/{stranger}/deactivate")).status_code == 404
        finally:
            await pool.close()
            _reset(app_main)
    import asyncio
    asyncio.run(run())
