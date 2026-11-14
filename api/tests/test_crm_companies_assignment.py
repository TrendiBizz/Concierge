"""Companies as a record, and who owns what.

Both were absent: `company` was stranded text on each contact, and no record had an owner, so a
team of two could not share a queue or ask "what is mine?". These run on Postgres, in one event
loop, through the real routes.
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
ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = (ROOT / "api" / "app" / "schema.sql").read_text()
import asyncio  # noqa: E402  (used inside each test's single loop)


async def _pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _tenant(slug="acme"):
    return await db.pool().fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
        slug, slug.title(), "pk" + uuid.uuid4().hex[:8])


async def _person(tenant, email="sam@acme.test", role="editor"):
    return await db.pool().fetchval(
        "INSERT INTO tenant_users (tenant_id, email, role, password_hash) VALUES ($1,$2,$3,'x') "
        "RETURNING id", tenant, email, role)


async def _contact(tenant, key="jo@example.test", name="Jo Bloggs"):
    return await db.pool().fetchval(
        "INSERT INTO customer_cases (tenant_id, case_key, display_name, primary_email) "
        "VALUES ($1,$2,$3,$2) RETURNING id", tenant, key, name)


def _client(tenant, user_id, email="owner@acme.test", role="owner"):
    from app import main as app_main
    user = {"id": str(user_id), "tenant_id": str(tenant), "email": email, "role": role,
            "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app),
                             base_url="http://test")


def _reset():
    from app import main as app_main
    app_main.app.dependency_overrides.clear()
    db._pool = None


def test_a_company_holds_people_and_reports_its_open_value():
    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            owner = await _person(tenant)
            contact = await _contact(tenant)
            async with _client(tenant, owner) as client:
                made = await client.post("/owner/companies",
                                          json={"name": "Pukeko Construction", "domain": "pukeko.co.nz"})
                assert made.status_code == 201, made.text
                company = made.json()["id"]
                linked = await client.put(f"/owner/contacts/jo@example.test/company",
                                          json={"company_id": company})
                assert linked.status_code == 200, linked.text
                # a deal attached to that person counts towards the company
                await pool.execute(
                    "INSERT INTO leads (tenant_id, channel, status, value_cents, case_id) "
                    "VALUES ($1,'email','contacted', 120000, $2)", tenant, contact)
                listed = await client.get("/owner/companies")
                row = listed.json()[0]
                assert row["name"] == "Pukeko Construction"
                assert row["contacts"] == 1 and row["open_deals"] == 1
                assert row["open_value_cents"] == 120000
                # deleting the company must not delete the person
                assert (await client.delete(f"/owner/companies/{company}")).status_code == 200
                assert await pool.fetchval(
                    "SELECT company_id FROM customer_cases WHERE id=$1", contact) is None
                assert await pool.fetchval("SELECT count(*) FROM customer_cases") == 1
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_a_company_is_tenant_scoped_and_names_are_unique():
    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme"), await _tenant("other")
            owner = await _person(mine)
            async with _client(mine, owner) as client:
                first = await client.post("/owner/companies", json={"name": "Acme Ltd"})
                assert first.status_code == 201
                again = await client.post("/owner/companies", json={"name": "Acme Ltd"})
                assert again.status_code == 409, "the same company twice would split its history"
            async with _client(theirs, await _person(theirs, "owner@other.test")) as other:
                listed = await other.get("/owner/companies")
                assert listed.json() == [], "another business must not see our companies"
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_assigning_someone_requires_them_to_be_on_this_team():
    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme"), await _tenant("other")
            me = await _person(mine, "me@acme.test")
            colleague = await _person(mine, "sam@acme.test")
            stranger = await _person(theirs, "stranger@other.test")
            lead = await pool.fetchval(
                "INSERT INTO leads (tenant_id, channel, status, name) VALUES ($1,'chat','new','Jo') "
                "RETURNING id", mine)
            async with _client(mine, me) as client:
                ok = await client.put(f"/owner/crm/leads/{lead}/assignee",
                                      json={"user_id": str(colleague)})
                assert ok.status_code == 200, ok.text
                assert ok.json()["assigned_to"] == str(colleague)
                bad = await client.put(f"/owner/crm/leads/{lead}/assignee",
                                       json={"user_id": str(stranger)})
                assert bad.status_code == 404, "a stranger from another business must not be assignable"
                cleared = await client.put(f"/owner/crm/leads/{lead}/assignee", json={"user_id": None})
                assert cleared.status_code == 200 and cleared.json()["assigned_to"] is None
            assert await pool.fetchval("SELECT assigned_to FROM leads WHERE id=$1", lead) is None
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_a_contact_can_be_given_an_owner_and_the_list_says_who():
    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            me = await _person(tenant, "me@acme.test")
            colleague = await _person(tenant, "sam@acme.test")
            await _contact(tenant)
            async with _client(tenant, me) as client:
                saved = await client.put("/owner/contacts/jo@example.test/assignee",
                                         json={"user_id": str(colleague)})
                assert saved.status_code == 200, saved.text
                listed = (await client.get("/owner/contacts")).json()["contacts"]
                assert listed[0]["assignee_email"] == "sam@acme.test"
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_the_pages_offer_the_new_records():
    shell = (ROOT / "web" / "portal" / "src" / "App.tsx").read_text()
    assert "{tab: 'companies', label: 'Companies'" in shell, "Companies is not in the navigation"
    companies = (ROOT / "web" / "portal" / "src" / "Companies.tsx").read_text()
    assert "'/owner/companies'" in companies
    contacts = (ROOT / "web" / "portal" / "src" / "CrmQuotes.tsx").read_text()
    assert "Account owner" in contacts and "Company" in contacts
    assert "/assignee" in contacts and "/company" in contacts


def test_the_contact_card_keeps_the_owner_it_just_saved():
    """The list reloaded but the open card did not, so the picker snapped back to "Nobody yet"
    straight after a successful save."""
    page = (ROOT / "web" / "portal" / "src" / "CrmQuotes.tsx").read_text()
    assign = page.split("async function setAssignee", 1)[1]
    assert "setSelected({...selected, assigned_to" in assign, "the card is not updated after saving the owner"
    company = page.split("async function setCompany", 1)[1]
    assert "setSelected({...selected, company_id" in company, "the card is not updated after saving the company"
