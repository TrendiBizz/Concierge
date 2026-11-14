"""The CRM could hold a pipeline but a salesperson could not move a deal, the "to-do" list was
read-only text, and erasing a customer left them in four other tables.

Everything runs in ONE event loop with httpx's ASGITransport. A FastAPI TestClient runs the app in
its own thread and loop, so a pool created by asyncio.run() in the test is bound to a dead loop and
the request hangs forever (see test_team.py, which learned this the hard way).
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


async def _pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _tenant(slug="acme", key="pk"):
    return await db.pool().fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
        slug, slug.title(), key + uuid.uuid4().hex[:6])


def _client(tenant, email="owner@acme.test", role="owner"):
    from app import main as app_main
    user = {"id": str(uuid.uuid4()), "tenant_id": str(tenant), "email": email,
            "role": role, "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app),
                             base_url="http://test")


def _reset():
    from app import main as app_main
    app_main.app.dependency_overrides.clear()
    db._pool = None


def test_a_deal_can_be_moved_and_valued_from_the_app():
    """`PATCH /owner/crm/leads/{id}` existed but no page called it: the pipeline was unreachable."""
    import asyncio

    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            lead = await pool.fetchval(
                "INSERT INTO leads (tenant_id, channel, status) VALUES ($1,'chat','new') RETURNING id",
                tenant)
            async with _client(tenant) as client:
                response = await client.patch(f"/owner/crm/leads/{lead}",
                                              json={"status": "won", "value_cents": 250_000})
                assert response.status_code == 200, response.text
            row = await pool.fetchrow("SELECT status, value_cents FROM leads WHERE id=$1", lead)
            assert row["status"] == "won" and row["value_cents"] == 250_000
            event = await pool.fetchrow(
                "SELECT to_status, actor FROM lead_events WHERE lead_id=$1 ORDER BY id DESC", lead)
            assert event["to_status"] == "won"
            assert event["actor"] == "owner@acme.test", "the history must say who moved it"
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_a_to_do_can_be_added_and_ticked_off_and_is_tenant_scoped():
    import asyncio

    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme", "pk1"), await _tenant("other", "pk2")
            async with _client(mine) as client:
                created = await client.post("/owner/tasks", json={"title": "Ring Jo back"})
                assert created.status_code == 201, created.text
                task_id = created.json()["id"]
                listed = await client.get("/owner/tasks")
                assert [row["title"] for row in listed.json()] == ["Ring Jo back"]
                done = await client.patch(f"/owner/tasks/{task_id}", json={"status": "done"})
                assert done.status_code == 200 and done.json()["status"] == "done"
                assert (await client.get("/owner/tasks")).json() == []
            async with _client(theirs, "owner@other.test") as other:
                assert (await other.patch(f"/owner/tasks/{task_id}", json={"status": "open"})).status_code == 404
                assert (await other.delete(f"/owner/tasks/{task_id}")).status_code == 404
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_erasing_a_customer_reaches_every_table_that_held_them():
    """The bug: erase blanked `leads` and reported "done" while the case, its whole conversation,
    the appointment and the quote still held the person."""
    import asyncio

    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            lead = await pool.fetchval(
                "INSERT INTO leads (tenant_id, channel, status, name, email, message) "
                "VALUES ($1,'chat','new','Jo Bloggs','jo@example.test','my driveway') RETURNING id",
                tenant)
            case = await pool.fetchval(
                "INSERT INTO customer_cases (tenant_id, case_key, display_name, primary_email) "
                "VALUES ($1,'jo@example.test','Jo Bloggs','jo@example.test') RETURNING id", tenant)
            await pool.execute("UPDATE leads SET case_id=$2 WHERE id=$1", lead, case)
            await pool.execute(
                "INSERT INTO case_events (tenant_id, case_id, channel, direction, body) "
                "VALUES ($1,$2,'email','inbound','my driveway is muddy')", tenant, case)
            await pool.execute(
                "INSERT INTO appointments (tenant_id, lead_id, starts_at, ends_at, name, email) "
                "VALUES ($1,$2, now() + interval '1 day', now() + interval '1 day 1 hour',"
                "'Jo Bloggs','jo@example.test')", tenant, lead)
            request = await pool.fetchval(
                "INSERT INTO privacy_requests (tenant_id, email, status) "
                "VALUES ($1,'jo@example.test','open') RETURNING id", tenant)
            async with _client(tenant) as client:
                response = await client.post(f"/owner/privacy/requests/{request}/erase")
                assert response.status_code == 200, response.text
            row = await pool.fetchrow(
                "SELECT display_name, primary_email, erased_at FROM customer_cases WHERE id=$1", case)
            assert row["display_name"] == "Erased" and row["primary_email"] == ""
            assert row["erased_at"] is not None, "the case was not marked erased"
            assert await pool.fetchval("SELECT body FROM case_events WHERE case_id=$1", case) == ""
            appointment = await pool.fetchrow("SELECT name, email FROM appointments WHERE lead_id=$1", lead)
            assert appointment["name"] == "Erased" and appointment["email"] == ""
            lead_row = await pool.fetchrow("SELECT name, email, erased_at FROM leads WHERE id=$1", lead)
            assert lead_row["name"] == "" and lead_row["erased_at"] is not None
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_the_crm_page_lets_you_move_a_deal_and_tick_off_a_to_do():
    page = (ROOT / "web" / "portal" / "src" / "CrmQuotes.tsx").read_text()
    assert "'/owner/crm/leads/' + lead.id, 'PATCH'" in page, "the pipeline is still read-only"
    assert "Deal stage" in page and "Deal value in dollars" in page
    assert "'/owner/tasks'" in page and "'/owner/tasks/' + todo.id, 'PATCH'" in page
    assert "What needs doing" in page, "the to-do list is still read-only text"
