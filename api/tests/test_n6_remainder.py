"""N6 Remainder tests:
- Studio UI for API keys & integrations
- Two-way Google Calendar pull sync (external move & cancel)
- Customer self-serve booking reschedule & cancel links
- Tradify & Fergus explicitly excluded from integrations
"""
from __future__ import annotations

import asyncio
import os
import pathlib
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import booking_links, calendar_connection, db, integrations, owner_auth, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "api" / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
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


def test_studio_integrations_and_api_keys_ui_wired():
    ui = (REPO_ROOT / "web/portal/src/Integrations.tsx").read_text(encoding="utf-8")
    for path in ("/owner/integrations", "/owner/api-keys", "/owner/integrations/servicem8/key"):
        assert path in ui
    app_tsx = (REPO_ROOT / "web/portal/src/App.tsx").read_text(encoding="utf-8")
    assert '<Tab value="integrations"' in app_tsx


@needs_db
def test_two_way_google_calendar_pull_and_customer_reschedule_cancel(monkeypatch):
    async def _go(pool):
        t = await tenants.create("Cal Co", "https://calco.example", "cal-co")
        inv = await owner_auth.make_invite(t["id"], "owner@calco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        t0 = datetime.now(timezone.utc) + timedelta(days=2)
        t1 = t0 + timedelta(hours=1)
        appt_move = await pool.fetchval(
            "INSERT INTO appointments(tenant_id, name, email, starts_at, ends_at, status) "
            "VALUES($1, 'Sam', 'sam@example.com', $2, $3, 'booked') RETURNING id",
            t["id"], t0, t1,
        )
        appt_cancel = await pool.fetchval(
            "INSERT INTO appointments(tenant_id, name, email, starts_at, ends_at, status) "
            "VALUES($1, 'Pat', 'pat@example.com', $2, $3, 'booked') RETURNING id",
            t["id"], t0, t1,
        )
        await pool.execute(
            "INSERT INTO calendar_connections(tenant_id, calendar_id, enabled) VALUES($1, 'primary', true)",
            t["id"],
        )

        # 1. Two-way Google Calendar pull sync
        moved_start = t0 + timedelta(hours=3)
        moved_end = moved_start + timedelta(hours=1)

        async def fake_request(tenant_id, method, path, **kwargs):
            return httpx.Response(200, json={"items": [
                {
                    "status": "confirmed",
                    "start": {"dateTime": moved_start.isoformat()},
                    "end": {"dateTime": moved_end.isoformat()},
                    "extendedProperties": {"private": {"concierge_appointment": str(appt_move)}},
                },
                {
                    "status": "cancelled",
                    "extendedProperties": {"private": {"concierge_appointment": str(appt_cancel)}},
                },
            ]})
        monkeypatch.setattr(calendar_connection, "request", fake_request)
        pulled = await calendar_connection.pull_changes_for_tenant(t["id"])
        assert pulled == {"updated": 1, "cancelled": 1}
        assert await pool.fetchval("SELECT status FROM appointments WHERE id=$1", appt_cancel) == "cancelled"

        # 2. Customer self-serve reschedule & cancel links
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            lnk = await client.get(f"/owner/appointments/{appt_move}/manage-link", headers=headers)
            assert lnk.status_code == 200
            token = lnk.json()["token"]

            page = await client.get(f"/booking/{token}")
            assert page.status_code == 200 and "Sam" in page.text

            new_start = (datetime.now(timezone.utc) + timedelta(days=4)).replace(microsecond=0)
            res = await client.post(f"/booking/{token}/reschedule", json={"starts_at": new_start.isoformat()})
            assert res.status_code == 200 and res.json()["status"] == "booked"

            can = await client.post(f"/booking/{token}/cancel")
            assert can.status_code == 200 and can.json()["status"] == "cancelled"
    run(_go)


def test_tradify_and_fergus_excluded_from_providers():
    assert "tradify" not in integrations.PROVIDERS
    assert "fergus" not in integrations.PROVIDERS
    assert set(integrations.PROVIDERS) == {"xero", "m365", "servicem8"}
