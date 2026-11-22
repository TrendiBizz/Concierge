"""N2 Privacy & Call-Recording Compliance tests:
- Full DSAR erasure across all tables (by email and by phone)
- Per-subject DSAR access export (including transcripts)
- Automated non-audio retention purge
- AU strict opt-in call-recording mode
- Privacy breach register (72h deadline) & privacy audit log
- Brevo unsubscribe suppression
"""
from __future__ import annotations

import asyncio
import os
import pathlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import asterisk_bridge, db, owner_auth, privacy_retention, suppressions, tenants
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


def test_au_strict_opt_in_call_recording_instructions():
    opt_out = asterisk_bridge.phone_instructions("Acme", recording_ok=True, listen_in=False, sms_ok=True, consent_mode="opt_out")
    assert "Our calls are recorded" in opt_out
    assert "Right after saying it, call set_call_recording with enabled=true" in opt_out

    opt_in = asterisk_bridge.phone_instructions("Acme", recording_ok=True, listen_in=False, sms_ok=True, consent_mode="strict_opt_in")
    assert "May I record this call" in opt_in
    assert "ONLY call set_call_recording with enabled=true and confirmed=true if they explicitly say yes" in opt_in
    assert "Right after saying it, call set_call_recording with enabled=true" not in opt_in


@needs_db
def test_full_dsar_export_and_erasure_across_all_tables():
    async def _go(pool):
        t = await tenants.create("priv-co", "Privacy Co", "")
        inv = await owner_auth.make_invite(t["id"], "owner@privco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        conv_id = await pool.fetchval(
            "INSERT INTO conversations(tenant_id, session_id) VALUES($1, 'sess-1') RETURNING id", t["id"]
        )
        await pool.execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES($1, 'user', 'My address is 42 Queen St')", conv_id
        )
        case_id = await pool.fetchval(
            "INSERT INTO customer_cases(tenant_id, case_key, display_name, primary_email, primary_phone) "
            "VALUES($1, 'case-1', 'Jane Doe', 'jane@example.com', '+64211234567') RETURNING id",
            t["id"],
        )
        await pool.execute(
            "INSERT INTO customer_addresses(tenant_id, case_id, kind, value) VALUES($1, $2, 'email', 'jane@example.com')",
            t["id"], case_id,
        )
        lead_id = await pool.fetchval(
            "INSERT INTO leads(tenant_id, conversation_id, case_id, name, email, phone, message) "
            "VALUES($1, $2, $3, 'Jane Doe', 'jane@example.com', '+64211234567', 'Need a quote') RETURNING id",
            t["id"], conv_id, case_id,
        )
        vs_id = await pool.fetchval(
            "INSERT INTO voice_sessions(tenant_id, conversation_id, token_hash, recording_consent) "
            "VALUES($1, $2, 'tokhash1', true) RETURNING id",
            t["id"], conv_id,
        )
        await pool.execute(
            "INSERT INTO voice_recordings(session_id, tenant_id, conversation_id, mime_type, audio, sha256) "
            "VALUES($1, $2, $3, 'audio/ogg', $4, 'deadbeef')",
            vs_id, t["id"], conv_id, b"OggS1234",
        )
        await pool.execute(
            "INSERT INTO call_insights(call_sid, tenant_id, lead_id, summary, outcome, sentiment, next_step) "
            "VALUES('CA123', $1, $2, 'Jane called about roof', 'resolved', 'positive', 'Call back')",
            t["id"], lead_id,
        )
        await pool.execute(
            "INSERT INTO email_drafts(tenant_id, sender, subject, inbound_body, reply_body) "
            "VALUES($1, 'jane@example.com', 'Roof quote', 'Hi from Jane', 'Sure Jane')",
            t["id"],
        )
        await pool.execute(
            "INSERT INTO outbox(tenant_id, kind, channel, to_addr, subject, body, lead_id) "
            "VALUES($1, 'reply', 'email', 'jane@example.com', 'Re: Roof', 'Hello Jane', $2)",
            t["id"], lead_id,
        )
        req_id = await pool.fetchval(
            "INSERT INTO privacy_requests(tenant_id, email, phone, kind) VALUES($1, 'jane@example.com', '+64211234567', 'delete') RETURNING id",
            t["id"],
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Per-subject access export includes transcripts, email_drafts, call_insights
            exp = await client.get(f"/owner/privacy/requests/{req_id}/export", headers=headers)
            assert exp.status_code == 200
            data = exp.json()
            assert len(data["leads"]) == 1
            assert any("42 Queen St" in m["content"] for m in data["messages"])
            assert len(data["email_drafts"]) == 1
            assert len(data["call_insights"]) == 1

            # 2. Full DSAR erasure removes/anonymizes across every table
            er = await client.post(f"/owner/privacy/requests/{req_id}/erase", headers=headers)
            assert er.status_code == 200
            summary = er.json()["summary"]
            assert summary["leads"] == 1
            assert summary["voice_recordings"] == 1
            assert summary["call_insights"] == 1
            assert summary["email_drafts"] == 1
            assert summary["outbox"] == 1

            assert await pool.fetchval("SELECT count(*) FROM voice_recordings WHERE tenant_id=$1", t["id"]) == 0
            assert await pool.fetchval("SELECT count(*) FROM customer_addresses WHERE tenant_id=$1", t["id"]) == 0
            assert await pool.fetchval("SELECT summary FROM call_insights WHERE tenant_id=$1", t["id"]) == ""
            assert await pool.fetchval("SELECT sender FROM email_drafts WHERE tenant_id=$1", t["id"]) == ""
            assert await pool.fetchval("SELECT to_addr FROM outbox WHERE tenant_id=$1", t["id"]) == ""

            # 3. Audit log recorded both export and erase
            aud = (await client.get("/owner/privacy/audit", headers=headers)).json()
            actions = {a["action"] for a in aud}
            assert "dsar_export" in actions and "dsar_erase" in actions
    run(_go)


@needs_db
def test_non_audio_retention_purge_recording_mode_breaches_and_brevo_unsub():
    async def _go(pool):
        t = await tenants.create("ret-co", "Retention Co", "")
        inv = await owner_auth.make_invite(t["id"], "owner@retco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        conv_id = await pool.fetchval(
            "INSERT INTO conversations(tenant_id, session_id) VALUES($1, 'old-s') RETURNING id", t["id"]
        )
        await pool.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES($1, 'user', 'Old message', now() - interval '400 days')", conv_id
        )
        await pool.execute(
            "INSERT INTO outbox(tenant_id, kind, channel, to_addr, subject, body, status, created_at) "
            "VALUES($1, 'reply', 'email', 'old@x.test', 'Old', 'Body', 'sent', now() - interval '200 days')", t["id"]
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Run retention purge via owner endpoint
            r = await client.post("/owner/privacy/retention/run", headers=headers)
            assert r.status_code == 200
            assert r.json()["purged"]["messages"] == 1
            assert r.json()["purged"]["outbox"] == 1

            # AU strict opt-in recording mode toggle
            rm = await client.put("/owner/privacy/recording-mode", headers=headers, json={"mode": "strict_opt_in"})
            assert rm.status_code == 200 and rm.json()["mode"] == "strict_opt_in"
            assert (await client.get("/owner/privacy/recording-mode", headers=headers)).json()["mode"] == "strict_opt_in"

            # Breach register with 72h deadline
            br = await client.post(
                "/owner/privacy/breaches", headers=headers,
                json={"title": "Misdirected email", "severity": "medium", "affected_count": 1},
            )
            assert br.status_code == 201
            bid = br.json()["id"]
            assert br.json()["due_72h_at"] is not None
            upd = await client.patch(f"/owner/privacy/breaches/{bid}", headers=headers, json={"status": "notified_opc"})
            assert upd.status_code == 200 and upd.json()["notified_at"] is not None

        # Brevo unsubscribed event suppresses the address
        res = await suppressions.record_event({"event": "unsubscribed", "email": "stop@example.com", "tenant_id": t["id"]})
        assert res["unsubscribed"] is True and res["suppressed"] is True
        assert await suppressions.is_suppressed(t["id"], "stop@example.com") is True
    run(_go)
