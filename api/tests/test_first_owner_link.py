"""A brand-new client must be able to get its owner in.

Creating a tenant and asking for the owner's link returned "Active user not found": recovery
deliberately refuses to invent a user, which is right for a lost password and wrong for the operator's
first step. Onboarding could not begin at all.

    docker run -d --name pgaddr -e POSTGRES_PASSWORD=pw -p 55433:5432 pgvector/pgvector:pg16
    TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
      python3 -m pytest tests/test_first_owner_link.py -q
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
    return pool


def test_a_new_client_gets_a_working_owner_invite():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        tenant = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
            "newco", "New Co", "pk_" + uuid.uuid4().hex[:8])

        link = await owner_auth.owner_link(tenant, "Owner@NewCo.Example")
        assert link["purpose"] == "invite", "a first owner must get an invite, not a recovery"
        assert link["role"] == "owner", "the first user has to be an owner, or nobody can administer"
        assert link["token"]

        # Someone who already exists keeps their own role: this must not escalate a viewer.
        await pool.execute("INSERT INTO tenant_users(tenant_id,email,role,password_hash) "
                           "VALUES($1,'viewer@newco.example','viewer','x')", tenant)
        again = await owner_auth.owner_link(tenant, "viewer@newco.example")
        assert again["purpose"] == "recovery"
        assert again["role"] == "viewer", "recovery must not promote an existing viewer"
        await pool.close()

    asyncio.run(run())
