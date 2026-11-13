"""Who can get in, and taking it away again.

The gap this closes: a business could invite staff but never revoke them, so a departed employee
kept their login. These tests run the real routes against a real Postgres, because the guarantees
are about rows and sessions, not about mocks.
"""
import asyncio
import os
import pathlib
import uuid

import asyncpg
import pytest

from app import db, owner_auth

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


def _client_for(user):
    from fastapi.testclient import TestClient
    from app import main as app_main
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return app_main.app, TestClient(app_main.app)


def _cleanup(app):
    app.dependency_overrides.clear()
    db._pool = None


@pytest.fixture
def team():
    """A tenant with one owner, one editor and one viewer."""
    async def setup():
        pool = await _fresh_pool()
        tenant = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
            "acme", "Acme", "pk_" + uuid.uuid4().hex[:8])
        people = {}
        for email, role in (("owner@acme.test", "owner"), ("editor@acme.test", "editor"),
                            ("gone@acme.test", "viewer")):
            people[role] = await pool.fetchval(
                "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
                "VALUES ($1,$2,$3,'x') RETURNING id", tenant, email, role)
        return pool, tenant, people
    pool, tenant, people = asyncio.run(setup())
    yield tenant, people
    asyncio.run(pool.close())
    db._pool = None


def _user(tenant, user_id, role="owner", email="owner@acme.test"):
    return {"id": str(user_id), "tenant_id": tenant, "email": email, "role": role,
            "slug": "acme", "name": "Acme"}


def test_the_team_list_shows_everyone_and_who_you_are(team):
    tenant, people = team
    app, client = _client_for(_user(tenant, people["owner"]))
    try:
        response = client.get("/owner/team")
        assert response.status_code == 200, response.text
        body = response.json()
        emails = {m["email"] for m in body["members"]}
        assert emails == {"owner@acme.test", "editor@acme.test", "gone@acme.test"}
        assert body["you"] == str(people["owner"])
        assert body["invitations"] == []
    finally:
        _cleanup(app)


def test_a_role_can_be_changed(team):
    tenant, people = team
    app, client = _client_for(_user(tenant, people["owner"]))
    try:
        response = client.patch(f"/owner/team/{people['viewer']}", json={"role": "editor"})
        assert response.status_code == 200, response.text
        assert response.json()["role"] == "editor"
        row = asyncio.run(db.pool().fetchrow(
            "SELECT role FROM tenant_users WHERE id=$1", people["viewer"]))
        assert row["role"] == "editor"
    finally:
        _cleanup(app)


def test_the_last_owner_cannot_be_removed_or_demoted(team):
    tenant, people = team
    app, client = _client_for(_user(tenant, people["owner"]))
    try:
        demote = client.patch(f"/owner/team/{people['owner']}", json={"role": "editor"})
        assert demote.status_code == 400
        assert "at least one owner" in demote.json()["detail"]

        # Removing yourself is refused before the owner rule, with its own message.
        remove_self = client.post(f"/owner/team/{people['owner']}/deactivate")
        assert remove_self.status_code == 400
        assert "your own access" in remove_self.json()["detail"]
    finally:
        _cleanup(app)


def test_deactivating_someone_ends_their_access_immediately(team):
    tenant, people = team

    async def plant_session():
        return await db.pool().fetchval(
            "INSERT INTO tenant_sessions (user_id, token_hash, expires_at) "
            "VALUES ($1, $2, now() + interval '30 days') RETURNING id",
            people["viewer"], "hash-" + uuid.uuid4().hex)

    app, client = _client_for(_user(tenant, people["owner"]))
    try:
        session_id = asyncio.run(plant_session())
        response = client.post(f"/owner/team/{people['viewer']}/deactivate")
        assert response.status_code == 200, response.text
        assert response.json()["active"] is False

        row = asyncio.run(db.pool().fetchrow(
            "SELECT active FROM tenant_users WHERE id=$1", people["viewer"]))
        assert row["active"] is False, "the account stayed active"

        left = asyncio.run(db.pool().fetchval(
            "SELECT count(*) FROM tenant_sessions WHERE id=$1", session_id))
        assert left == 0, "an existing session survived deactivation"

        # And they can come back, with the same history, if they are re-hired.
        again = client.post(f"/owner/team/{people['viewer']}/reactivate")
        assert again.status_code == 200 and again.json()["active"] is True
    finally:
        _cleanup(app)


def test_only_an_owner_can_change_the_team(team):
    tenant, people = team
    app, client = _client_for(_user(tenant, people["editor"], role="editor",
                                    email="editor@acme.test"))
    try:
        assert client.get("/owner/team").status_code == 200  # everyone may look
        blocked = client.patch(f"/owner/team/{people['viewer']}", json={"role": "owner"})
        assert blocked.status_code == 403, "an editor promoted someone to owner"
        assert client.post(f"/owner/team/{people['viewer']}/deactivate").status_code == 403
    finally:
        _cleanup(app)


def test_a_person_from_another_business_cannot_be_touched(team):
    tenant, people = team

    async def other_tenant_user():
        other = await db.pool().fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
            "other", "Other", "pk_" + uuid.uuid4().hex[:8])
        return await db.pool().fetchval(
            "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
            "VALUES ($1,'x@other.test','editor','x') RETURNING id", other)

    app, client = _client_for(_user(tenant, people["owner"]))
    try:
        stranger = asyncio.run(other_tenant_user())
        response = client.patch(f"/owner/team/{stranger}", json={"role": "viewer"})
        assert response.status_code == 404, "cross-tenant write was allowed"
        assert client.post(f"/owner/team/{stranger}/deactivate").status_code == 404
    finally:
        _cleanup(app)
