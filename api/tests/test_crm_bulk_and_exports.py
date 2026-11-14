"""Bulk assignment, the CSV export, saved replies, and the company hierarchy.

Each closes a gap the audit named: a team could only reassign one contact at a time, the reports
could not leave the app, there was no template library, and companies had a parent column with no
way to set it.
"""
import asyncio
import io
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


def _client(tenant, user_id=None, email="owner@acme.test", role="owner"):
    from app import main as app_main
    user = {"id": str(user_id or uuid.uuid4()), "tenant_id": str(tenant), "email": email,
            "role": role, "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app),
                             base_url="http://test")


def _reset():
    from app import main as app_main
    app_main.app.dependency_overrides.clear()
    db._pool = None


async def _tenant(slug="acme"):
    return await db.pool().fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$2,$3) RETURNING id",
        slug, slug.title(), "pk" + uuid.uuid4().hex[:8])


def test_a_batch_of_contacts_can_be_given_one_owner():
    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            member = await pool.fetchval(
                "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
                "VALUES ($1,'sam@acme.test','editor','x') RETURNING id", tenant)
            for key in ("a@example.test", "b@example.test", "c@example.test"):
                await pool.execute(
                    "INSERT INTO customer_cases (tenant_id, case_key, display_name, primary_email) "
                    "VALUES ($1,$2,$2,$2)", tenant, key)
            async with _client(tenant) as client:
                done = await client.post("/owner/contacts/bulk-assign", json={
                    "case_keys": ["a@example.test", "b@example.test"], "user_id": str(member)})
                assert done.status_code == 200, done.text
                assert done.json()["updated"] == 2
            owners = await pool.fetch(
                "SELECT case_key, assigned_to FROM customer_cases ORDER BY case_key")
            assert [str(r["assigned_to"]) for r in owners] == [str(member), str(member), "None"]
            async with _client(tenant) as client:
                cleared = await client.post("/owner/contacts/bulk-assign", json={
                    "case_keys": ["a@example.test", "b@example.test"], "user_id": None})
                assert cleared.json()["updated"] == 2
            assert await pool.fetchval("SELECT count(*) FROM customer_cases WHERE assigned_to IS NOT NULL") == 0
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_a_foreign_batch_cannot_be_assigned_into_our_business():
    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme"), await _tenant("other")
            stranger = await pool.fetchval(
                "INSERT INTO tenant_users (tenant_id, email, role, password_hash) "
                "VALUES ($1,'x@other.test','owner','x') RETURNING id", theirs)
            await pool.execute(
                "INSERT INTO customer_cases (tenant_id, case_key, display_name) VALUES ($1,'a@x.test','A')",
                mine)
            async with _client(mine) as client:
                refused = await client.post("/owner/contacts/bulk-assign",
                                            json={"case_keys": ["a@x.test"], "user_id": str(stranger)})
                assert refused.status_code == 404
            assert await pool.fetchval("SELECT assigned_to FROM customer_cases") is None
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_the_report_can_leave_the_app_with_lost_reasons_and_sources():
    async def run():
        pool = await _pool()
        try:
            tenant = await _tenant()
            for status, channel, reason, value in (
                    ("lost", "email", "too expensive", 0),
                    ("won", "chat", "", 250000),
                    ("new", "voice", "", 90000)):
                await pool.execute(
                    "INSERT INTO leads (tenant_id, channel, status, lost_reason, value_cents) "
                    "VALUES ($1,$2,$3,$4,$5)", tenant, channel, status, reason, value)
            await pool.execute(
                "INSERT INTO quotations (tenant_id, lead_id, title, lines, currency, status, total_cents, "
                "contact, tax_basis_points, tax_cents, subtotal_cents) "
                "SELECT $1, id, 'Deck', '[]'::jsonb, 'NZD', 'accepted', 123400, '{}'::jsonb, "
                "1500, 0, 123400 FROM leads LIMIT 1", tenant)
            async with _client(tenant) as client:
                response = await client.get("/owner/reports/export.csv?days=30")
                assert response.status_code == 200, response.text
                assert response.headers["content-type"].startswith("text/csv")
                assert "attachment; filename=concierge-report.csv" in response.headers["content-disposition"]
                text = response.text
            assert text.splitlines()[0] == "section,stage_or_status,channel,lost_reason,count,value_cents"
            assert "too expensive" in text, "lost reasons must be in the export"
            assert "enquiries,new,voice" in text, "the source channel must be in the export"
            assert "quotes,accepted" in text, "quotes by status must be in the export"
            import csv
            rows = list(csv.DictReader(io.StringIO(text)))
            assert rows and all(row["section"] for row in rows)
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_saved_replies_can_be_written_reused_and_deleted():
    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme"), await _tenant("other")
            async with _client(mine) as client:
                made = await client.post("/owner/email-templates", json={
                    "name": "Quote follow-up", "subject": "Your quote",
                    "body": "Hi, just checking you saw the quote."})
                assert made.status_code == 201, made.text
                tidy = made.json()["id"]
                assert [t["name"] for t in (await client.get("/owner/email-templates")).json()] == ["Quote follow-up"]
                duplicate = await client.post("/owner/email-templates",
                                              json={"name": "Quote follow-up", "body": "x"})
                assert duplicate.status_code == 409
                edited = await client.patch(f"/owner/email-templates/{tidy}",
                                            json={"name": "Quote chase", "subject": "", "body": "Second try."})
                assert edited.status_code == 200 and edited.json()["name"] == "Quote chase"
                assert (await client.delete(f"/owner/email-templates/{tidy}")).status_code == 200
                assert (await client.get("/owner/email-templates")).json() == []
            async with _client(theirs, email="owner@other.test") as other:
                assert (await other.get("/owner/email-templates")).json() == []
                assert (await other.delete(f"/owner/email-templates/{tidy}")).status_code == 404
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_a_branch_company_points_at_its_parent_and_refuses_another_business():
    async def run():
        pool = await _pool()
        try:
            mine, theirs = await _tenant("acme"), await _tenant("other")
            async with _client(mine) as client:
                parent = (await client.post("/owner/companies", json={"name": "Pukeko Holdings"})).json()["id"]
                branch = (await client.post("/owner/companies", json={"name": "Pukeko Construction"})).json()["id"]
                linked = await client.patch(f"/owner/companies/{branch}", json={"parent_id": parent})
                assert linked.status_code == 200, linked.text
                assert linked.json()["parent_id"] == str(parent)
            async with _client(theirs, email="owner@other.test") as other:
                stranger = (await other.post("/owner/companies", json={"name": "Not Yours"})).json()["id"]
            async with _client(mine) as client:
                refused = await client.patch(f"/owner/companies/{branch}", json={"parent_id": stranger})
                assert refused.status_code == 404, "a parent from another business must be refused"
                # un-nesting is a real instruction. This answered "Nothing to update" and left
                # the old parent in place, so a branch could never be made independent again.
                alone = await client.patch(f"/owner/companies/{branch}", json={"parent_id": None})
                assert alone.status_code == 200, alone.text
                assert alone.json()["parent_id"] is None
                relisted = {c["id"]: c for c in (await client.get("/owner/companies")).json()}
                assert relisted[branch]["parent_id"] is None
        finally:
            _reset()
            await pool.close()
    asyncio.run(run())


def test_the_pages_offer_these_controls():
    contacts = (ROOT / "web" / "portal" / "src" / "CrmQuotes.tsx").read_text()
    assert "Assign selected" in contacts and "/owner/contacts/bulk-assign" in contacts
    reports = (ROOT / "web" / "portal" / "src" / "App.tsx").read_text()
    assert "/owner/reports/export.csv" in reports, "the reports page cannot export"
    replies = (ROOT / "web" / "portal" / "src" / "SavedReplies.tsx").read_text()
    assert "/owner/email-templates" in replies
    assert "{tab: 'replies', label: 'Saved replies'" in reports, "saved replies has no page of its own"
    assert "SavedReplies token={token}" in reports
    companies = (ROOT / "web" / "portal" / "src" / "Companies.tsx").read_text()
    assert "Stands alone" in companies, "no way to nest a company"


def test_every_dropdown_has_a_name_a_screen_reader_can_read():
    """A <select> with no label and no aria-label is announced as "combo box", nothing more.

    This found Designs.tsx, whose customer picker sat under a paragraph instead of a label.
    """
    import re
    pages = pathlib.Path(ROOT / "web" / "portal" / "src")
    offenders = []
    for page in pages.glob("*.tsx"):
        source = page.read_text()
        for match in re.finditer(r"<select\b", source):
            # A tag can contain ">" inside an arrow function, so look at a window of the tag
            # rather than a naive regex to the next ">".
            window = source[match.start():match.start() + 400]
            if "aria-label" in window.split(">\n")[0]:
                continue
            before = source[:match.start()]
            # inside a <label>…</label> means the label names it by wrapping it
            if before.rfind("<label") > before.rfind("</label>"):
                continue
            offenders.append(f"{page.name}: <select{attrs[:40]}>")
    assert offenders == [], "dropdowns with no accessible name: " + "; ".join(offenders)
