"""N14 Voice Operational Essentials tests:
- Business-hours routing (API + Asterisk GotoIfTime dialplan)
- Caller blocklist & spam rate-limit (API + Asterisk Hangup(21) dialplan)
- Warm transfer with brief (API + call_control + Asterisk warm-transfer context)
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
from datetime import datetime, timezone

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import call_control, db, owner_auth, tenants, voice_routing
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "api" / "app" / "schema.sql").read_text()


def _load_render_routes():
    spec = importlib.util.spec_from_file_location("render_routes", REPO_ROOT / "scripts/asterisk/render_routes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_business_hours_window_and_block_pattern():
    sched = {"mon": ["08:30", "17:00"], "sat": [], "sun": []}
    # Monday 10:00 NZDT = Sunday 21:00 UTC (NZDT is UTC+13 in Nov)
    mon_10_nz = datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc)
    mon_19_nz = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)
    sun_10_nz = datetime(2026, 11, 21, 21, 0, tzinfo=timezone.utc)
    assert voice_routing.is_within_business_hours(sched, "Pacific/Auckland", now=mon_10_nz) is True
    assert voice_routing.is_within_business_hours(sched, "Pacific/Auckland", now=mon_19_nz) is False
    assert voice_routing.is_within_business_hours(sched, "Pacific/Auckland", now=sun_10_nz) is False

    assert voice_routing.matches_block_pattern("+6490012345", "+64900*") is True
    assert voice_routing.matches_block_pattern("+6421123456", "+64900*") is False
    assert voice_routing.matches_block_pattern("anonymous", "anonymous") is True


def test_asterisk_render_routes_business_hours_blocklist_and_warm_transfer():
    rr = _load_render_routes()
    trunk = {"server": "sip.hero.co.nz", "username": "6498881234", "password": "testpassword123"}
    rows = [{
        "tenant": "acme",
        "number": "+6498881234",
        "port": 9001,
        "ring_owner": {"number": "+64211234567", "seconds": 15, "hours": "08:30-17:00,mon-fri,*,*"},
        "blocked_callers": ["+64900111222"],
    }]
    ext, _ = rr.render(rows, "bridge", trunk=trunk)
    assert "GotoIfTime(08:30-17:00,mon-fri,*,*?rf_hours_ok:rf_skip)" in ext
    assert 'GotoIf($["${CONCIERGE_CID}"="64900111222"]?blocked)' in ext
    assert "(blocked),Hangup(21)" in ext
    assert "[business-acme-warm-transfer]" in ext
    assert "CONCIERGE_WARM_BRIEF" in ext


@needs_db
def test_voice_routing_blocklist_and_warm_transfer_api(monkeypatch):
    async def _go(pool):
        t = await tenants.create("voice-co", "Voice Co", "")
        inv = await owner_auth.make_invite(t["id"], "owner@voiceco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Save business-hours routing
            r = await client.put("/owner/voice/routing", headers=headers, json={
                "business_hours": {"mon": ["08:30", "17:00"], "tue": ["08:30", "17:00"], "wed": [], "thu": [], "fri": [], "sat": [], "sun": []},
                "timezone": "Pacific/Auckland",
                "during_hours_action": "ring_owner_then_ai",
                "after_hours_action": "ai_only",
                "ring_owner_number": "+64211234567",
                "ring_seconds": 20,
                "spam_max_calls_10m": 3,
            })
            assert r.status_code == 200
            mon_10_nz = datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc)
            mon_19_nz = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)
            ev_in = await voice_routing.evaluate_inbound_call(t["id"], "+64219998888", now=mon_10_nz)
            assert ev_in["action"] == "ring_owner_then_ai" and ev_in["within_hours"] is True
            ev_out = await voice_routing.evaluate_inbound_call(t["id"], "+64219998888", now=mon_19_nz)
            assert ev_out["action"] == "ai_only" and ev_out["within_hours"] is False

            # Blocklist CRUD + evaluation
            bl = await client.post("/owner/voice/blocklist", headers=headers, json={"phone_pattern": "+64900*", "reason": "Telemarketer"})
            assert bl.status_code == 201
            entry_id = bl.json()["id"]
            ev_blk = await voice_routing.evaluate_inbound_call(t["id"], "+64900555111", now=mon_10_nz)
            assert ev_blk["action"] == "block" and ev_blk["blocked"] is True
            assert (await client.delete(f"/owner/voice/blocklist/{entry_id}", headers=headers)).status_code == 200
            ev_unblk = await voice_routing.evaluate_inbound_call(t["id"], "+64900555111", now=mon_10_nz)
            assert ev_unblk["blocked"] is False

            # Warm transfer calls call_control.warm_transfer_call with brief
            captured = {}
            async def fake_warm(call_sid, slug, number, *, brief="", config=None):
                captured.update({"call_sid": call_sid, "slug": slug, "number": number, "brief": brief})
                return "PJSIP/concierge-reg-0001"
            monkeypatch.setattr(call_control, "warm_transfer_call", fake_warm)
            wt = await client.post(
                "/owner/voice/calls/ast:11111111-2222-3333-4444-555555555555/warm-transfer",
                headers=headers,
                json={"number": "+64211234567", "brief": "VIP roof leak caller Jane"},
            )
            assert wt.status_code == 200
            assert captured["brief"] == "VIP roof leak caller Jane"
            assert captured["slug"] == "voice-co"
            assert await pool.fetchval("SELECT count(*) FROM voice_warm_transfers WHERE tenant_id=$1", t["id"]) == 1
    run(_go)
