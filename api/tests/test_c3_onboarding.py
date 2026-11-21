"""C3: self-serve onboarding and activation showstoppers.

1. Stripe-provisioned owners (password_hash='') must count as the tenant's owner principal.
2. "Take over" on a web-chat lead must silence the streaming chat for that visitor.
3. Appointments must send confirmations/reminders without a connected calendar.
4. Studio must expose the knowledge base and privacy requests; the invite names real tabs.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
from unittest.mock import AsyncMock

import asyncpg
import pytest

from app import calendar_connection, channel_authorization, chat, casetimeline, db, owner_invites

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
APP = pathlib.Path(__file__).resolve().parents[1] / "app"
SCHEMA = (APP / "schema.sql").read_text()
REPO = pathlib.Path(__file__).resolve().parents[2]


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


async def _tenant(pool, slug):
    return await pool.fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1,$1,$2) RETURNING id", slug, "pk_" + slug)


@needs_db
def test_provisioned_owner_with_empty_password_hash_is_the_owner_principal():
    async def run():
        pool = await _fresh_pool()
        try:
            tid = await _tenant(pool, "acme")
            await pool.execute(
                "INSERT INTO tenant_users(tenant_id,email,role,password_hash,active) "
                "VALUES($1,'o@acme.test','owner','',true)", tid)
            owner = await channel_authorization.ownership(tid)
            assert owner is not None, "a Stripe-provisioned owner was excluded by password_hash<>''"
            # An inactive owner is still not a principal.
            await pool.execute("UPDATE tenant_users SET active=false WHERE tenant_id=$1", tid)
            assert await channel_authorization.ownership(tid) is None
        finally:
            await db._pool.close()
    asyncio.run(run())


async def _chat_lead(pool, tid, session, paused):
    case = await pool.fetchrow(
        "INSERT INTO customer_cases(tenant_id,case_key,display_name,primary_email,automation_paused) "
        "VALUES($1,'email:x@y.test','X','x@y.test',$2) RETURNING id", tid, paused)
    conv = await pool.fetchval(
        "INSERT INTO conversations(tenant_id,session_id,channel) VALUES($1,$2,'chat') RETURNING id", tid, session)
    await pool.execute(
        "INSERT INTO leads(tenant_id,conversation_id,email,channel,source_key,case_id) "
        "VALUES($1,$2,'x@y.test','chat','k',$3)", tid, conv, case["id"])


@needs_db
def test_takeover_is_found_from_the_chat_session_and_scoped_to_tenant():
    async def run():
        pool = await _fresh_pool()
        try:
            a, b = await _tenant(pool, "a"), await _tenant(pool, "b")
            await _chat_lead(pool, a, "sess-paused", True)
            assert await casetimeline.is_paused_for_session(a, "sess-paused") is True
            assert await casetimeline.is_paused_for_session(b, "sess-paused") is False
            assert await casetimeline.is_paused_for_session(a, "other-session") is False
            await pool.execute("UPDATE customer_cases SET automation_paused=false")
            assert await casetimeline.is_paused_for_session(a, "sess-paused") is False
        finally:
            await db._pool.close()
    asyncio.run(run())


@needs_db
def test_streaming_chat_stays_silent_after_takeover_and_keeps_the_message(monkeypatch):
    async def run():
        pool = await _fresh_pool()
        try:
            tid = await _tenant(pool, "acme")
            await _chat_lead(pool, tid, "sess-1", True)
            boom = AsyncMock(side_effect=AssertionError("the model must not be called"))
            monkeypatch.setattr(chat.llm, "stream_complete", boom)
            monkeypatch.setattr(chat.enquiries, "capture", AsyncMock())
            tenant = {"id": tid, "slug": "acme", "name": "acme", "default_country_code": "64"}
            events = [e async for e in chat.run_turn_stream(tenant, "sess-1", "chat", "hello?")]
            assert events[-1]["suppressed"] is True and events[-1]["reason"] == "human_takeover"
            assert not any(e["type"] == "token" for e in events if "type" in e)
            saved = await pool.fetchval("SELECT count(*) FROM messages WHERE role='user' AND content='hello?'")
            assert saved == 1, "the visitor's message was lost during takeover"
        finally:
            await db._pool.close()
    asyncio.run(run())


async def _appointment(pool, tid, state, attempts=0):
    return await pool.fetchval(
        "INSERT INTO appointments(tenant_id,starts_at,ends_at,name,email,consent_contact,"
        "calendar_state,calendar_attempts,calendar_sync_requested) "
        "VALUES($1, now()+interval '3 days', now()+interval '3 days 1 hour','Hana','h@x.test',true,$2,$3,true) "
        "RETURNING id", tid, state, attempts)


@needs_db
def test_appointment_notices_go_out_without_a_connected_calendar(monkeypatch):
    async def run():
        pool = await _fresh_pool()
        try:
            tid = await _tenant(pool, "acme")
            fired = AsyncMock()
            from app import automation
            monkeypatch.setattr(automation, "on_appointment_booked", fired)
            for state, expect in (("unconnected", True), ("needs_contact", True),
                                  ("synced", True), ("retry", False), ("pending", False)):
                fired.reset_mock()
                appt = await _appointment(pool, tid, state)
                await calendar_connection.notify_synced(appt)
                assert (fired.await_count == 1) is expect, state
                done = await pool.fetchval("SELECT calendar_notice_done FROM appointments WHERE id=$1", appt)
                assert done is expect, state
                # Never twice for the same appointment.
                await calendar_connection.notify_synced(appt)
                assert fired.await_count == (1 if expect else 0), state
            # A calendar that has used up its retries must not leave the customer unconfirmed.
            fired.reset_mock()
            appt = await _appointment(pool, tid, "retry", attempts=10)
            await calendar_connection.notify_synced(appt)
            assert fired.await_count == 1
        finally:
            await db._pool.close()
    asyncio.run(run())


def test_studio_has_knowledge_and_privacy_tabs_and_the_invite_names_real_tabs():
    app = (REPO / "web/portal/src/App.tsx").read_text()
    for tab in ("knowledge", "privacy"):
        assert f"tab: '{tab}'" in app and f"tab === '{tab}'" in app, tab
    knowledge = (REPO / "web/portal/src/Knowledge.tsx").read_text()
    assert "/owner/knowledge/import-website" in knowledge
    privacy = (REPO / "web/portal/src/Privacy.tsx").read_text()
    for path in ("/owner/privacy/requests", "/erase", "/consent"):
        assert path in privacy, path
    # The first-run email must not send owners to a tab that does not exist.
    assert 'Open "Business"' not in pathlib.Path(owner_invites.__file__).read_text()
