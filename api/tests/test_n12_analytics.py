"""N12 Analytics tests: AI resolution rate, response-time SLAs (p50/p95), CSAT, date-range reporting."""
from __future__ import annotations

import asyncio
import os
import pathlib
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, owner_auth, tenants
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


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


@needs_db
def test_n12_analytics_resolution_sla_csat_and_date_range():
    async def _go(pool):
        t = await tenants.create("Ana Co", "https://anaco.example", "ana-co")
        inv = await owner_auth.make_invite(t["id"], "owner@anaco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        now = datetime.now(timezone.utc)
        # Conversation 1: AI resolved in 4 seconds
        c1 = await pool.fetchval(
            "INSERT INTO conversations(tenant_id, session_id, started_at) VALUES($1, 's1', $2) RETURNING id",
            t["id"], now - timedelta(hours=2),
        )
        await pool.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES "
            "($1, 'user', 'Hours?', $2), ($1, 'assistant', '8am-5pm', $3)",
            c1, now - timedelta(hours=2), now - timedelta(hours=2) + timedelta(seconds=4),
        )
        # Conversation 2: Human took over after 10 seconds
        c2 = await pool.fetchval(
            "INSERT INTO conversations(tenant_id, session_id, started_at) VALUES($1, 's2', $2) RETURNING id",
            t["id"], now - timedelta(hours=1),
        )
        await pool.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES "
            "($1, 'user', 'Custom quote', $2), ($1, 'owner', 'I will call you', $3)",
            c2, now - timedelta(hours=1), now - timedelta(hours=1) + timedelta(seconds=10),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Submit 2 CSAT responses via public endpoint
            r1 = await client.post("/api/v1/csat", json={"key": t["public_key"], "session_id": "s1", "rating": 5, "comment": "Fast!"})
            r2 = await client.post("/api/v1/csat", json={"key": t["public_key"], "session_id": "s2", "rating": 4})
            assert r1.status_code == 201 and r2.status_code == 201

            # Query date-range analytics
            d0 = (now - timedelta(days=7)).date().isoformat()
            d1 = now.date().isoformat()
            res = await client.get(f"/owner/analytics/summary?from_date={d0}&to_date={d1}", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["ai_resolution"]["total_conversations"] == 2
            assert data["ai_resolution"]["ai_resolved"] == 1
            assert data["ai_resolution"]["human_escalated"] == 1
            assert data["ai_resolution"]["resolution_rate_pct"] == 50.0
            assert data["response_sla"]["sample_count"] == 2
            assert data["response_sla"]["p50_seconds"] == 7.0
            assert data["response_sla"]["within_sla_pct"] == 100.0
            assert data["csat"]["responses"] == 2
            assert data["csat"]["average_rating"] == 4.5
            assert data["csat"]["satisfied_pct"] == 100.0
            assert len(data["daily"]) >= 1
    run(_go)
