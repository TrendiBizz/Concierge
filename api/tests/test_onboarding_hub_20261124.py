"""Tests for the 7-stage Concierge Onboarding Hub (Phase 1 API/Studio + Phase 2 /guide page)."""
from __future__ import annotations

import asyncio
import os
import pathlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import chat, db, owner_auth, tenants
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


@needs_db
def test_onboarding_hub_progress_sandbox_test_alert_and_slot_preview(monkeypatch):
    async def go(pool):
        t = await tenants.create("Guide Co", "https://guideco.example", "guide-co")
        await pool.execute(
            "UPDATE tenants SET notify_email='owner@guideco.example', timezone='America/Chicago', "
            "native_booking=true, business_hours='{\"mon\":[[\"09:00\",\"17:00\"]],\"tue\":[[\"09:00\",\"17:00\"]],\"wed\":[[\"09:00\",\"17:00\"]],\"thu\":[[\"09:00\",\"17:00\"]],\"fri\":[[\"09:00\",\"17:00\"]]}'::jsonb "
            "WHERE id=$1",
            t["id"],
        )
        inv = await owner_auth.make_invite(t["id"], "owner@guideco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async def fake_turn(tenant, session_id, channel, message, *, dry_run=False, **kw):
            assert dry_run is True
            return {"reply": f"Grounded reply to: {message}"}
        monkeypatch.setattr(chat, "run_turn", fake_turn)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. GET initial progress + live auto_checks
            r0 = await client.get("/owner/onboarding/progress", headers=headers)
            assert r0.status_code == 200
            d0 = r0.json()
            assert d0["current_stage"] == 1
            assert d0["auto_checks"]["identity"] is True
            assert d0["auto_checks"]["alerts_configured"] is True

            # 2. PUT progress + launch
            r1 = await client.put(
                "/owner/onboarding/progress",
                headers=headers,
                json={"completed_steps": ["identity", "alerts", "bogus_ignored"], "current_stage": 3, "launched": True},
            )
            assert r1.status_code == 200
            d1 = r1.json()
            assert d1["current_stage"] == 3
            assert set(d1["completed_steps"]) == {"identity", "alerts", "launch"}
            assert d1["launched_at"] is not None

            # 3. POST sandbox test-chat (dry_run=True, zero leads created)
            r2 = await client.post("/owner/onboarding/test-chat", headers=headers, json={"message": "What are your hours?"})
            assert r2.status_code == 200
            assert r2.json()["dry_run"] is True
            assert "What are your hours?" in r2.json()["reply"]
            assert await pool.fetchval("SELECT count(*) FROM leads WHERE tenant_id=$1", t["id"]) == 0

            # 4. POST test-alert queues a clearly labeled [TEST] email
            r3 = await client.post("/owner/onboarding/test-alert", headers=headers)
            assert r3.status_code == 200 and r3.json()["queued"] is True
            out_row = await pool.fetchrow(
                "SELECT channel, subject, to_addr FROM outbox WHERE tenant_id=$1 AND kind='owner_alert'",
                t["id"],
            )
            assert out_row["channel"] == "email" and "[TEST]" in out_row["subject"]
            assert out_row["to_addr"] == "owner@guideco.example"

            # 5. GET preview-slots returns real available slots
            r4 = await client.get("/owner/onboarding/preview-slots?days=7", headers=headers)
            assert r4.status_code == 200
            assert r4.json()["timezone"] == "America/Chicago"
            assert isinstance(r4.json()["slots"], list)
    run(go)


def test_studio_and_public_guide_page_wired():
    hub = (REPO_ROOT / "web/portal/src/OnboardingHub.tsx").read_text(encoding="utf-8")
    drawer = (REPO_ROOT / "web/portal/src/TabGuideDrawer.tsx").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "website/guide.html").read_text(encoding="utf-8")
    for path in ("/owner/onboarding/progress", "/owner/onboarding/test-chat", "/owner/onboarding/test-alert", "/owner/onboarding/preview-slots"):
        assert path in hub
    assert "TAB_GUIDES" in drawer and "https://trendibizz.com/guide" in drawer
    assert "/media/concierge-explainer.mp4" in guide
    assert "USD $199/month" in guide
    assert "Tradify" not in guide and "Fergus" not in guide
