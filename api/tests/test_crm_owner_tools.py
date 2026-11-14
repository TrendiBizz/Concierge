"""The CRM could hold a pipeline but a salesperson could not move a deal, and the "to-do" list
was read-only text. Both are fixed here; the guarantees are about rows, so these run on Postgres.

Also covers the erasure hole: the first erase blanked `leads` and stopped, leaving the customer in
`customer_cases`, `case_events`, `appointments` and `quotations` while reporting "done".
"""
import asyncio
import os
import pathlib
import uuid

import asyncpg
import pytest

from app import db

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()
ROOT = pathlib.Path(__file__).resolve().parents[2]


async def _fresh():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


def _client(**user):
    from fastapi.testclient import TestClient
    from app import main
    from app import owner_auth
    main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return main.app, TestClient(main.app)


def test_a_deal_can_be_moved_and_valued_from_the_app():
    """`PATCH /owner/crm/leads/{id}` existed but no page called it: the pipeline was unreachable."""
    async def setup():
        pool = await _fresh()
        tenant = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ('acme','Acme','pk') RETURNING id")
        lead = await pool.fetchval(
            "INSERT INTO leads (tenant_id, channel, status) VALUES ($1,'chat','new') RETURNING id", tenant)
        return pool, tenant, lead
    pool, tenant, lead = asyncio.run(setup())
    async def check():
        app, client = _client(id=str(uuid.uuid4()), tenant_id=str(tenant),
                              email="owner@acme.test", role="owner", slug="acme")
        try:
            response = client.patch(f"/owner/crm/leads/{lead}",
                                     json={"status": "won", "value_cents": 250_000})
            assert response.status_code == 200, response.text
            row = await pool.fetchrow("SELECT status, value_cents FROM leads WHERE id=$1", lead)
            assert row["status"] == "won" and row["value_cents"] == 250_000
            event = await pool.fetchrow(
                "SELECT to_status, actor FROM lead_events WHERE lead_id=$1 ORDER BY id DESC", lead)
            assert event["to_status"] == "won"
            assert event["actor"] == "owner@acme.test", "the history must say who moved it"
        finally:
            app.dependency_overrides.clear()
    asyncio.run(check())
    asyncio.run(pool.close())
    db._pool = None


def test_a_to_do_can_be_added_ticked_off_and_is_tenant_scoped():
    async def setup():
        pool = await _fresh()
        mine = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ('acme','Acme','pk1') RETURNING id")
        theirs = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ('other','Other','pk2') RETURNING id")
        return pool, mine, theirs
    pool, mine, theirs = asyncio.run(setup())

    async def check():
        app, client = _client(id=str(uuid.uuid4()), tenant_id=str(mine),
                              email="owner@acme.test", role="owner", slug="acme")
        try:
            created = client.post("/owner/tasks", json={"title": "Ring Jo back"})
            assert created.status_code == 201, created.text
            task_id = created.json()["id"]
            listed = client.get("/owner/tasks")
            assert [row["title"] for row in listed.json()] == ["Ring Jo back"]
            done = client.patch(f"/owner/tasks/{task_id}", json={"status": "done"})
            assert done.status_code == 200 and done.json()["status"] == "done"
            assert client.get("/owner/tasks").json() == []
        finally:
            app.dependency_overrides.clear()
        # another business cannot touch it
        app2, other = _client(id=str(uuid.uuid4()), tenant_id=str(theirs),
                               email="owner@other.test", role="owner", slug="other")
        try:
            assert other.patch(f"/owner/tasks/{task_id}", json={"status": "open"}).status_code == 404
            assert other.delete(f"/owner/tasks/{task_id}").status_code == 404
        finally:
            app2.dependency_overrides.clear()
    asyncio.run(check())
    asyncio.run(pool.close())
    db._pool = None


def test_erasing_a_customer_reaches_every_table_that_held_them():
    """The bug: erase blanked `leads` and left cases, events, appointments and quotes intact."""
    async def setup():
        pool = await _fresh()
        tenant = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key) VALUES ('acme','Acme','pk') RETURNING id")
        lead = await pool.fetchval(
            "INSERT INTO leads (tenant_id, channel, status, name, email, message) "
            "VALUES ($1,'chat','new','Jo Bloggs','jo@example.test','my driveway') RETURNING id", tenant)
        case = await pool.fetchval(
            "INSERT INTO customer_cases (tenant_id, case_key, display_name, primary_email) "
            "VALUES ($1,'jo@example.test','Jo Bloggs','jo@example.test') RETURNING id", tenant)
        await pool.execute("UPDATE leads SET case_id=$2 WHERE id=$1", lead, case)
        await pool.execute(
            "INSERT INTO case_events (tenant_id, case_id, channel, direction, body) "
            "VALUES ($1,$2,'email','inbound','my driveway is muddy')", tenant, case)
        await pool.execute(
            "INSERT INTO appointments (tenant_id, lead_id, starts_at, ends_at, name, email) "
            "VALUES ($1,$2, now() + interval '1 day', now() + interval '1 day 1 hour','Jo Bloggs','jo@example.test')",
            tenant, lead)
        await pool.execute(
            "INSERT INTO quotations (tenant_id, lead_id, title, lines, currency) "
            "VALUES ($1,$2,'Driveway','[]','NZD')", tenant, lead)
        request = await pool.fetchval(
            "INSERT INTO privacy_requests (tenant_id, email, status) "
            "VALUES ($1,'jo@example.test','open') RETURNING id", tenant)
        return pool, tenant, lead, case, request
    pool, tenant, lead, case, request = asyncio.run(setup())

    async def check():
        app, client = _client(id=str(uuid.uuid4()), tenant_id=str(tenant),
                              email="owner@acme.test", role="owner", slug="acme")
        try:
            response = client.post(f"/owner/privacy/requests/{request}/erase")
            assert response.status_code == 200, response.text
            row = await pool.fetchrow("SELECT display_name, primary_email, erased_at FROM customer_cases WHERE id=$1", case)
            assert row["display_name"] == "Erased" and row["primary_email"] == ""
            assert row["erased_at"] is not None
            body = await pool.fetchval("SELECT body FROM case_events WHERE case_id=$1", case)
            assert body == "", "the conversation survived the erasure"
            appointment = await pool.fetchrow("SELECT name, email FROM appointments WHERE lead_id=$1", lead)
            assert appointment["name"] == "Erased" and appointment["email"] == ""
            lead_row = await pool.fetchrow("SELECT name, email, erased_at FROM leads WHERE id=$1", lead)
            assert lead_row["name"] == "" and lead_row["erased_at"] is not None
        finally:
            app.dependency_overrides.clear()
    asyncio.run(check())
    asyncio.run(pool.close())
    db._pool = None


def test_the_crm_page_lets_you_move_a_deal_and_tick_off_a_to_do():
    page = (ROOT / "web" / "portal" / "src" / "CrmQuotes.tsx").read_text()
    assert "'/owner/crm/leads/' + lead.id, 'PATCH'" in page, "the pipeline is still read-only"
    assert "Deal stage" in page and "Deal value in dollars" in page
    assert "'/owner/tasks'" in page and "'/owner/tasks/' + todo.id, 'PATCH'" in page
    assert "What needs doing" in page, "the to-do list is still read-only text"
