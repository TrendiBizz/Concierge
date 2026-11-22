"""Tier 2 Feature tests (H1, H2, H3, H4, H5, H6, H8, H9, H10, H11; H7 skipped)."""
from __future__ import annotations

import asyncio
import base64
import os
import pathlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, owner_auth, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "api" / "app" / "schema.sql").read_text()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "test-admin-token")


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


def test_h4_prechat_h9_widget_i18n_and_h6_studio_webhook_field():
    widget = (REPO_ROOT / "api/static/widget.js").read_text(encoding="utf-8")
    assert "data-prechat" in widget
    assert "WIDGET_I18N" in widget and "data-lang" in widget and "Pātai mai" in widget
    ui = (REPO_ROOT / "web/portal/src/Integrations.tsx").read_text(encoding="utf-8")
    assert "/owner/team-chat-webhook" in ui


@needs_db
def test_tier2_end_to_end_h1_h2_h3_h5_h6_h8_h10_h11(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: type("S", (), {"admin_token": ADMIN_TOKEN})())
    monkeypatch.setattr("app.public_fetch.validate_public_https_url", lambda u: u)
    monkeypatch.setattr(get_settings(), "outbound_ai_calls_enabled", False, raising=False)

    async def _go(pool):
        t = await tenants.create("Tier2 Co", "https://tier2.example", "tier2-co")
        inv = await owner_auth.make_invite(t["id"], "owner@tier2.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # H6: Slack/Teams webhook config
            wh = await client.put("/owner/team-chat-webhook", headers=headers, json={"url": "https://hooks.slack.com/services/T0/B0/XX"})
            assert wh.status_code == 200 and "hooks.slack.com" in wh.json()["url"]

            # H1: Visitor photo upload & owner fetch
            up = await client.post("/api/v1/chat/upload", json={
                "key": t["public_key"], "session_id": "s1", "filename": "leak.png",
                "content_type": "image/png", "content_base64": base64.b64encode(b"\x89PNG\r\n\x1a\n1234").decode(),
            })
            assert up.status_code == 201
            uid = up.json()["id"]
            dl = await client.get(f"/owner/chat-uploads/{uid}", headers=headers)
            assert dl.status_code == 200 and dl.content.startswith(b"\x89PNG")

            # H2: GBP review draft & approve
            rev_id = await pool.fetchval(
                "INSERT INTO gbp_reviews(tenant_id, external_review_id, reviewer_name, rating, comment) "
                "VALUES($1, 'rev-1', 'Tama', 5, 'Great work!') RETURNING id", t["id"],
            )
            dr = await client.post(f"/owner/reviews/{rev_id}/draft-reply", headers=headers)
            assert dr.status_code == 200 and "Tama" in dr.json()["ai_draft_reply"]
            ap = await client.post(f"/owner/reviews/{rev_id}/approve", headers=headers)
            assert ap.status_code == 200 and ap.json()["reply_status"] == "approved"

            # H3: Multi-staff scheduling
            st = await client.post("/owner/staff", headers=headers, json={
                "name": "Hemi Plumber", "service_types": ["drainage", "gas"], "slot_minutes": 45, "buffer_minutes": 15,
            })
            assert st.status_code == 201
            assert len((await client.get("/owner/staff", headers=headers)).json()) == 1

            # H5: Custom CRM stages & contact tags
            stg = await client.put("/owner/crm/stages", headers=headers, json={
                "stages": [{"slug": "site_visit", "label": "Site Visit", "colour": "#0ea5e9"},
                           {"slug": "quoted", "label": "Quoted", "colour": "#10b981"}],
            })
            assert stg.status_code == 200 and len(stg.json()["stages"]) == 2
            case_id = await pool.fetchval(
                "INSERT INTO customer_cases(tenant_id, case_key, display_name) VALUES($1, 'c1', 'Mere') RETURNING id", t["id"]
            )
            assert (await client.post(f"/owner/contacts/{case_id}/tags", headers=headers, json={"tag": "vip"})).status_code == 201
            assert (await client.get(f"/owner/contacts/{case_id}/tags", headers=headers)).json()["tags"] == ["vip"]

            # H8: SSE stream returns text/event-stream connected event
            sse = await client.get("/owner/events/stream?once=1", headers=headers)
            assert sse.status_code == 200 and "text/event-stream" in sse.headers["content-type"]
            assert "event: connected" in sse.text

            # H10: Outbound AI calls OFF by default (409), queues when enabled
            assert (await client.post("/owner/voice/outbound-calls", headers=headers, json={
                "to_number": "+64211234567", "purpose": "booking_confirmation",
            })).status_code == 409
            monkeypatch.setattr(get_settings(), "outbound_ai_calls_enabled", True, raising=False)
            oc = await client.post("/owner/voice/outbound-calls", headers=headers, json={
                "to_number": "+64211234567", "purpose": "booking_confirmation",
            })
            assert oc.status_code == 201 and oc.json()["status"] == "queued"

            # H11: Partner RBAC scoped to linked tenants only
            pr = await client.post("/admin/partners", headers={"X-Admin-Token": ADMIN_TOKEN}, json={
                "name": "Agency NZ", "email": "ops@agency.nz",
            })
            assert pr.status_code == 201
            ptok = pr.json()["token"]
            pid = pr.json()["id"]
            assert (await client.post(f"/admin/partners/{pid}/tenants", headers={"X-Admin-Token": ADMIN_TOKEN}, json={
                "tenant_id": str(t["id"]), "role": "editor",
            })).status_code == 201
            pt = await client.get("/partner/tenants", headers={"X-Partner-Token": ptok})
            assert pt.status_code == 200 and len(pt.json()["tenants"]) == 1 and pt.json()["tenants"][0]["slug"] == "tier2-co"
    run(_go)
