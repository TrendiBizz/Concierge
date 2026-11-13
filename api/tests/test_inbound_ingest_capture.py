"""A verified inbound email must become a customer, with the details written in the message.

`inbound_email.ingest_verified` used `email_signature` without importing it, so every real inbound
email raised NameError and the API answered 400 — no draft, no lead, no customer. Nothing caught it,
because the tests around inbound mail exercised helpers and never the ingestion path itself.

    docker run -d --name pgaddr -e POSTGRES_PASSWORD=pw -p 55433:5432 pgvector/pgvector:pg16
    TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
      python3 -m pytest tests/test_inbound_ingest_capture.py -q
"""
import asyncio
import os
import pathlib
import uuid

import asyncpg
import pytest

from app import db, inbound_email

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")

SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    return pool


def test_verified_inbound_email_becomes_a_customer():
    async def run():
        pool = await _fresh_pool()
        db._pool = pool
        tenant = await pool.fetchval(
            "INSERT INTO tenants (slug, name, public_key, reply_address, default_country_code) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING id",
            "harbour", "Harbour", "pk_" + uuid.uuid4().hex[:8], "reply-test@trendibizz.com", "64")
        await pool.execute("INSERT INTO tenant_channel_authorizations(tenant_id, channel, authorized) "
                           "VALUES($1,'email_read',true)", tenant)
        await pool.execute("INSERT INTO inbound_mailboxes(recipient, tenant_id, provider, enabled) "
                           "VALUES('reply-test@trendibizz.com',$1,'cloudflare',true)", tenant)

        draft = await inbound_email.ingest_verified(
            tenant, "cloudflare", "msg-1@harbourjoinery.example.nz",
            "harbour@harbourjoinery.example.nz", "reply-test@trendibizz.com",
            "Quote for kitchen joinery",
            "Hi, quote please.\n\nKind regards,\nMarcus Whitcombe\nHarbour Joinery\n027 555 8801",
            auth={"spf": "pass", "dkim": "pass", "dmarc": "pass", "aligned": "yes"},
            risk="low", flags=[], envelope_from=None)

        assert draft["sender"] == "harbour@harbourjoinery.example.nz"
        case = await pool.fetchrow(
            "SELECT display_name, company, primary_phone, primary_email FROM customer_cases "
            "WHERE tenant_id=$1", tenant)
        assert case, "the inbound email never became a customer"
        assert case["display_name"] == "Marcus Whitcombe", "the signature name was lost"
        assert case["company"] == "Harbour Joinery", "the signature company was lost"
        assert case["primary_phone"] == "+64275558801", "the signature phone was lost"
        events = await pool.fetchval("SELECT count(*) FROM case_events WHERE tenant_id=$1", tenant)
        assert events == 1, "the email is not on the customer's history"
        await pool.close()

    asyncio.run(run())
