"""A customer reachable at several addresses is still one customer.

Against a real Postgres, because the whole point is SQL behaviour: matching on every known address,
the unique (tenant, kind, value) identity, and merging without tripping that index. Skipped when
TEST_DATABASE_URL is unset, so the unit suite still runs anywhere.

    docker run -d --name pgaddr -e POSTGRES_PASSWORD=pw -p 55433:5432 pgvector/pgvector:pg16
    TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
      python3 -m pytest tests/test_customer_addresses.py -q
"""
import asyncio
import os
import pathlib
import uuid

import asyncpg
import pytest

from app import casetimeline, db

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


def test_one_customer_many_addresses():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        try:
            t = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
                "acme", "Acme", "pk_test_" + uuid.uuid4().hex[:8])

            # First sighting: a phone call.
            first = await casetimeline.reconcile(t, phone="+6491234567", default_cc="64")
            assert first["case_key"].startswith("phone:")

            # An email we have never seen, arriving alone, is NOT assumed to be the same person:
            # guessing would merge unrelated strangers. It becomes its own case until something
            # links it.
            stranger = await casetimeline.reconcile(t, email="hana@acme.co.nz", default_cc="64")
            assert stranger["id"] != first["id"]

            # With both identifiers in hand, they are linked -- and the merged case now knows both.
            linked = await casetimeline.reconcile(
                t, phone="+6491234567", email="hana@acme.co.nz", default_cc="64")
            assert linked["id"] == first["id"], "the phone identity should survive the merge"

            # From here on, either address alone resolves to that one customer. This is the whole
            # point: a work email is no longer a separate stranger.
            by_email = await casetimeline.reconcile(t, email="hana@acme.co.nz", default_cc="64")
            assert by_email["id"] == first["id"], "a known email did not resolve to the customer"

            # And a second number, once added, resolves the same way.
            await casetimeline.add_address(t, first["id"], kind="phone",
                                           value="+64211234567", default_cc="64")
            again = await casetimeline.reconcile(t, phone="+64211234567", default_cc="64")
            assert again["id"] == first["id"], "a second phone made a new customer"

            addresses = await casetimeline.list_addresses(t, first["id"])
            values = {(a["kind"], a["value"]) for a in addresses}
            assert ("phone", "+6491234567") in values
            assert ("email", "hana@acme.co.nz") in values
            assert ("phone", "+64211234567") in values
            assert len(values) == 3

            # A stranger with a different number and email is a different customer.
            other = await casetimeline.reconcile(t, phone="+6499999999", email="bob@x.co.nz", default_cc="64")
            assert other["id"] != first["id"]
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())


def test_adding_and_removing_addresses():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        try:
            t = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
                "acme", "Acme", "pk_" + uuid.uuid4().hex[:8])
            case = await casetimeline.reconcile(t, phone="+6491234567", default_cc="64")

            added = await casetimeline.add_address(t, case["id"], kind="email",
                                                   value="Hana@Acme.CO.NZ", label="work")
            assert added["value"] == "hana@acme.co.nz", "email was not normalised"
            assert added["label"] == "work"

            with pytest.raises(ValueError, match="valid email"):
                await casetimeline.add_address(t, case["id"], kind="email", value="not-an-email")
            with pytest.raises(ValueError, match="phone number"):
                await casetimeline.add_address(t, case["id"], kind="phone", value="abc")

            # Another customer's address cannot be claimed.
            other = await casetimeline.reconcile(t, phone="+6499999999", default_cc="64")
            with pytest.raises(ValueError, match="another customer"):
                await casetimeline.add_address(t, other["id"], kind="phone", value="+6491234567")

            # The last address may never be removed: that customer would become unfindable.
            for a in await casetimeline.list_addresses(t, case["id"]):
                if a["kind"] == "email":
                    assert await casetimeline.remove_address(t, case["id"], a["id"]) is True
            with pytest.raises(ValueError, match="at least one address"):
                await casetimeline.remove_address(t, case["id"], case["id"] and
                    (await casetimeline.list_addresses(t, case["id"]))[0]["id"])
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())


def test_merging_two_cases_carries_their_addresses():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        try:
            t = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
                "acme", "Acme", "pk_" + uuid.uuid4().hex[:8])
            phone_case = await casetimeline.reconcile(t, phone="+6491234567", default_cc="64")
            email_case = await casetimeline.ensure_case(t, email="hana@acme.co.nz", default_cc="64")
            assert email_case["id"] != phone_case["id"]

            merged = await casetimeline.reconcile(
                t, phone="+6491234567", email="hana@acme.co.nz", default_cc="64")
            assert merged["id"] == phone_case["id"], "the phone identity should survive"

            addresses = await casetimeline.list_addresses(t, merged["id"])
            assert {a["value"] for a in addresses} == {"+6491234567", "hana@acme.co.nz"}
            left = await pool.fetchval("SELECT count(*) FROM customer_cases WHERE tenant_id=$1", t)
            assert left == 1, "the duplicate customer was not removed"
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())


def test_an_imported_address_says_it_came_from_the_import():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        try:
            t = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
                "acme", "Acme", "pk_" + uuid.uuid4().hex[:8])
            await casetimeline.reconcile(t, phone="+64210888999", default_cc="64", source="import")
            row = await pool.fetchrow(
                "SELECT source FROM customer_addresses WHERE tenant_id=$1", t)
            assert row["source"] == "import", "an imported address claimed a different origin"
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(run())
