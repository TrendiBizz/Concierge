"""A reply to one customer must leave everyone else's unanswered work intact."""
import asyncio
import os
import uuid

import asyncpg
import pytest

from app import casetimeline


def _run_check(monkeypatch, check):
    async def run():
        port = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
        try:
            conn = await asyncpg.connect(
                f"postgresql://postgres:test@127.0.0.1:{port}/postgres", timeout=5)
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"No test PostgreSQL available: {exc}")
        schema = "reply_scope_" + uuid.uuid4().hex
        try:
            await conn.execute(f"CREATE SCHEMA {schema}; SET search_path TO {schema}")
            await conn.execute("""
                CREATE TABLE customer_cases (
                    id uuid PRIMARY KEY, tenant_id uuid, case_key text,
                    primary_phone text, primary_email text, updated_at timestamptz
                );
                CREATE TABLE case_events (
                    id serial PRIMARY KEY, tenant_id uuid, case_id uuid,
                    channel text, source_key text, direction text,
                    answered_at timestamptz
                );
            """)
            monkeypatch.setattr(casetimeline.db, "pool", lambda: conn)
            tenant, other_tenant, alice, bob, outsider = [uuid.uuid4() for _ in range(5)]
            for tid, case_id, phone, email in (
                (tenant, alice, "+6421555123", "alice@example.com"),
                (tenant, bob, "+6421555999", "bob@example.com"),
                (other_tenant, outsider, "+6421555123", "alice@example.com"),
            ):
                await conn.execute(
                    "INSERT INTO customer_cases VALUES($1,$2,$3,$4,$5,now())",
                    case_id, tid, "phone:" + phone, phone, email)
                for channel in ("email", "sms"):
                    await conn.execute(
                        "INSERT INTO case_events(tenant_id,case_id,channel,source_key,direction) "
                        "VALUES($1,$2,$3,$4,'inbound')",
                        tid, case_id, channel, str(case_id) + channel)
            await check(conn, tenant, alice, bob, outsider)
        finally:
            await conn.execute(f"DROP SCHEMA {schema} CASCADE")
            await conn.close()
    asyncio.run(run())


def test_reply_only_answers_that_customers_channel(monkeypatch):
    async def check(conn, tenant, alice, bob, outsider):
        # The case is keyed by phone but the reply knows only its email alias.
        await casetimeline.mark_replied(
            tenant, email="ALICE@example.com", channel="email", default_cc="64")
        answered = await conn.fetch("SELECT case_id, channel FROM case_events WHERE answered_at IS NOT NULL")
        assert [(r["case_id"], r["channel"]) for r in answered] == [(alice, "email")]
    _run_check(monkeypatch, check)


def test_reply_without_customer_identity_answers_nobody(monkeypatch):
    async def check(conn, tenant, alice, bob, outsider):
        await casetimeline.mark_replied(tenant, channel="email")
        assert await conn.fetchval("SELECT count(*) FROM case_events WHERE answered_at IS NOT NULL") == 0
    _run_check(monkeypatch, check)


def test_exact_source_key_only_answers_its_message(monkeypatch):
    async def check(conn, tenant, alice, bob, outsider):
        count = await casetimeline.mark_answered(
            tenant, channel="sms", source_key=str(alice) + "sms")
        assert count == 1
        assert await conn.fetchval("SELECT count(*) FROM case_events WHERE answered_at IS NOT NULL") == 1
    _run_check(monkeypatch, check)
