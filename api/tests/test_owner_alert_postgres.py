"""Owner alerts against a REAL Postgres built from app/schema.sql (no fake pool, no SQL-text asserts).

Needs a throwaway server: CONCIERGE_TEST_POSTGRES_PORT (default 55432), user postgres / password "test"
or trust auth. The pgvector column is swapped for float8[] when the extension is missing. Skipped when
no server answers.
"""
import asyncio
import os
import re
import uuid
from pathlib import Path

import asyncpg
import pytest

from app import channel_health, channel_authorization, db, outbox, owner_notifications as on

PORT = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
SCHEMA = Path(__file__).resolve().parent.parent / "app" / "schema.sql"


def _dsn(name="postgres"):
    return f"postgresql://postgres:test@127.0.0.1:{PORT}/{name}"


def _schema_sql():
    sql = SCHEMA.read_text()
    sql = sql.replace("CREATE EXTENSION IF NOT EXISTS vector;", "")
    sql = sql.replace("vector(__DIM__)", "float8[]")
    return re.sub(r"^CREATE INDEX[^\n]*hnsw[^\n]*\n", "", sql, flags=re.M)


@pytest.fixture(scope="module")
def dbname():
    async def make():
        try:
            admin = await asyncpg.connect(_dsn(), timeout=5)
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"No test PostgreSQL available: {exc}")
        name = "alerts_" + uuid.uuid4().hex[:12]
        await admin.execute(f"CREATE DATABASE {name}")
        await admin.close()
        conn = await asyncpg.connect(_dsn(name))
        await conn.execute(_schema_sql())
        await conn.close()
        return name

    async def drop(name):
        admin = await asyncpg.connect(_dsn())
        await admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        await admin.close()

    name = asyncio.run(make())
    yield name
    asyncio.run(drop(name))


def run(dbname, monkeypatch, scenario):
    """Run ``scenario(conn, tenant)`` on a clean database state with the app pointed at it."""
    async def go():
        conn = await asyncpg.connect(_dsn(dbname))
        try:
            await conn.execute("TRUNCATE outbox, leads, tenants CASCADE")
            tid = await conn.fetchval(
                "INSERT INTO tenants(slug,name,public_key,notify_email,notify_phone,sms_enabled,sms_transport) "
                "VALUES('t','Harbour Dental','pk','owner@example.co.nz','+64210000001',true,'device') RETURNING id")
            tenant = dict(await conn.fetchrow("SELECT * FROM tenants WHERE id=$1", tid))
            monkeypatch.setattr(db, "pool", lambda: conn)
            monkeypatch.setattr(channel_authorization, "is_authorized", _true)
            monkeypatch.setattr(on, "_spawn_push", lambda *a, **k: None)
            await scenario(conn, tenant)
        finally:
            await conn.close()
    asyncio.run(go())


async def _true(*a, **k):
    return True


async def _lead(conn, tenant, message="hello", channel="chat"):
    return await conn.fetchval(
        "INSERT INTO leads(tenant_id,message,channel) VALUES($1,$2,$3) RETURNING id", tenant["id"], message, channel)


async def _rows(conn, order="id"):
    return await conn.fetch("SELECT * FROM outbox WHERE kind='owner_alert' ORDER BY " + order)


def test_thirty_turns_of_one_conversation_make_one_email_and_one_text(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t)
        for turn in range(30):
            await on.queue(t, "Chat conversation for Harbour Dental", f"Enquirer: question {turn}",
                           f"dialogue:{t['id']}:k{turn}", lead_id=lead, connection=conn)
        rows = await _rows(conn)
        assert sorted(r["channel"] for r in rows) == ["email", "sms"]
        assert all("question 29" in r["body"] for r in rows)          # latest words, whole conversation
        assert all(r["status"] == "pending" and r["send_at"] > r["created_at"] for r in rows)  # debounced
    run(dbname, monkeypatch, scenario)


def test_the_enquiry_alert_and_the_dialogue_alert_seconds_apart_merge(dbname, monkeypatch):
    """Prod 21 Nov: 6153 (enquiry) and 6155 (dialogue) for one conversation, 7 s apart."""
    async def scenario(conn, t):
        lead = await _lead(conn, t, "How much does Concierge cost?")
        await on.queue(t, "Chat enquiry for Harbour Dental", "Channel: chat\nEmail: \nPhone: \n\nHow much does Concierge cost?",
                       "enquiry-original:x", lead_id=lead, connection=conn)
        await on.queue(t, "Chat conversation for Harbour Dental", "Enquirer: How much does Concierge cost?\n\nConcierge: $250",
                       "dialogue:x", lead_id=lead, connection=conn)
        email = [r for r in await _rows(conn) if r["channel"] == "email"]
        assert len(email) == 1 and "$250" in email[0]["body"]
    run(dbname, monkeypatch, scenario)


def test_after_an_alert_is_sent_the_next_turn_waits_for_the_window_and_is_not_dropped(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t)
        await on.queue(t, "Chat enquiry", "Enquirer: first", "d1", lead_id=lead, connection=conn)
        await conn.execute("UPDATE outbox SET status='sent', sent_at=now()")
        await on.queue(t, "Chat enquiry", "Enquirer: second", "d2", lead_id=lead, connection=conn)
        await on.queue(t, "Chat enquiry", "Enquirer: third", "d3", lead_id=lead, connection=conn)
        pending = await conn.fetch("SELECT * FROM outbox WHERE status='pending' AND channel='email'")
        assert len(pending) == 1 and "third" in pending[0]["body"]       # second+third merged, nothing lost
        wait = await conn.fetchval("SELECT extract(epoch FROM send_at - now()) FROM outbox WHERE id=$1", pending[0]["id"])
        assert 240 < wait <= 300                                          # at most one alert per 300 s window
    run(dbname, monkeypatch, scenario)


def test_different_conversations_stay_separate_with_distinct_subjects(dbname, monkeypatch):
    async def scenario(conn, t):
        a, b = await _lead(conn, t, "How much does Concierge cost?"), await _lead(conn, t, "Is there a yearly plan?")
        await on.queue(t, "Chat enquiry for Harbour Dental", "Channel: chat\nEmail: \nPhone: \n\nHow much does Concierge cost?",
                       "e1", lead_id=a, connection=conn)
        await on.queue(t, "Chat enquiry for Harbour Dental", "Channel: chat\nEmail: \nPhone: \n\nIs there a yearly plan?",
                       "e2", lead_id=b, connection=conn)
        email = [r for r in await _rows(conn) if r["channel"] == "email"]
        assert len(email) == 2
        assert len({r["subject"] for r in email}) == 2
        assert all("How much" in r["subject"] or "yearly plan" in r["subject"] for r in email)
    run(dbname, monkeypatch, scenario)


def test_automated_mail_is_email_only_and_never_falls_back(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t, channel="email")
        await on.queue(t, "Email enquiry for Harbour Dental", "Channel: email\nEmail: care@yellow.co.nz\nPhone: \n\nListing inquiry",
                       "enquiry-original:y", lead_id=lead, connection=conn, automated=True)
        rows = await _rows(conn)
        assert [r["channel"] for r in rows] == ["email"] and rows[0]["dedupe_key"].endswith(":auto")
        await conn.execute("UPDATE outbox SET status='failed'")   # even a failed one is not re-sent by SMS
        assert await channel_health.escalate_failed_owner_alerts() == 0
        assert len(await _rows(conn)) == 1
    run(dbname, monkeypatch, scenario)


def test_failed_sms_falls_back_to_email_only_when_the_twin_email_was_not_sent(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(channel_health, "db", db)
        for n, email_status in (("a", "sent"), ("b", "failed")):
            key = f"enquiry-original:{n}"
            await conn.execute(
                "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,status) VALUES"
                "($1,'owner_alert','email','owner@example.co.nz','S','body',$2,$3),"
                "($1,'owner_alert','sms','+64210000001','','body',$4,'failed')",
                t["id"], key, email_status, key + ":sms")
        await channel_health.escalate_failed_owner_alerts()
        fb = await conn.fetch("SELECT dedupe_key FROM outbox WHERE dedupe_key LIKE 'fb:%'")
        # twin "a" was delivered -> no duplicate; twin "b" never arrived -> its email IS re-sent (via the failed
        # email's own SMS fallback and the failed SMS's email fallback); nothing is produced for "a".
        sms_ids = {r["id"]: r["dedupe_key"] for r in await conn.fetch("SELECT id,dedupe_key FROM outbox WHERE channel='sms'")}
        fb_sources = {int(r["dedupe_key"].split(":")[1]) for r in fb}
        assert not any(sms_ids.get(i, "").startswith("enquiry-original:a") for i in fb_sources)
        assert any(sms_ids.get(i, "").startswith("enquiry-original:b") for i in fb_sources)
    run(dbname, monkeypatch, scenario)


def test_three_unconfirmed_texts_in_a_row_stop_texting_until_the_probe_interval(dbname, monkeypatch):
    async def scenario(conn, t):
        async def texts(*ages_hours_and_status):
            await conn.execute("DELETE FROM outbox")
            for i, (hours, status) in enumerate(ages_hours_and_status):
                await conn.execute(
                    "INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,last_error,created_at) VALUES"
                    "($1,'owner_alert','sms','+64210000001','b',$2,$3, now() - make_interval(hours => $4))",
                    t["id"], status, "Phone did not confirm send; reconcile before retry" if status == "failed" else "", hours)
        await texts((0.1, "failed"), (0.5, "failed"), (1, "failed"))
        assert await on.sms_unconfirmable(conn, t["id"])
        await texts((3, "failed"), (4, "failed"), (5, "failed"))            # probe interval passed
        assert not await on.sms_unconfirmable(conn, t["id"])
        await texts((0.1, "failed"), (0.5, "sent"), (1, "failed"))           # one got through
        assert not await on.sms_unconfirmable(conn, t["id"])
        await texts((0.1, "failed"), (0.5, "failed"), (1, "failed"))
        await on.queue(t, "S", "Channel: chat\nEmail: \nPhone: \n\nhi", "k1", lead_id=await _lead(conn, t), connection=conn)
        assert await conn.fetchval("SELECT count(*) FROM outbox WHERE dedupe_key='k1'") == 1   # only the email
        assert await conn.fetchval("SELECT count(*) FROM outbox WHERE dedupe_key='k1:sms'") == 0
    run(dbname, monkeypatch, scenario)


def test_a_phone_calls_start_and_end_alerts_become_one(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t, "Inbound telephone enquiry", channel="phone")
        await on.queue(t, "Phone enquiry for Harbour Dental", "Channel: phone\nEmail: \nPhone: \n\nInbound telephone enquiry",
                       "enquiry-original:call", lead_id=lead, connection=conn, hold_seconds=300)
        held = await conn.fetchval("SELECT extract(epoch FROM send_at - now()) FROM outbox WHERE channel='email'")
        assert 250 < held <= 300                                          # waits for the call to end
        await on.queue(t, "Phone message for Harbour Dental", "I need a quote for a deck.\n\nThe complete enquiry is saved in your CRM.",
                       "call-1:owner", lead_id=lead, connection=conn, finalize=True)
        rows = await conn.fetch("SELECT * FROM outbox WHERE channel='email'")
        assert len(rows) == 1 and "quote for a deck" in rows[0]["body"]
        assert await conn.fetchval("SELECT extract(epoch FROM send_at - now()) FROM outbox WHERE channel='email'") <= 45
    run(dbname, monkeypatch, scenario)


def test_a_call_that_leaves_no_message_still_alerts(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t, "Inbound telephone enquiry", channel="phone")
        await on.queue(t, "Phone enquiry for Harbour Dental", "Channel: phone\nEmail: \nPhone: \n\nInbound telephone enquiry",
                       "enquiry-original:call", lead_id=lead, connection=conn, hold_seconds=300)
        await conn.execute("UPDATE outbox SET send_at = now()")
        due = await conn.fetch("SELECT id FROM outbox WHERE status='pending' AND send_at <= now()")  # outbox worker's query
        assert len(due) == 2
    run(dbname, monkeypatch, scenario)


def test_distinct_subject_is_unique_per_enquiry_and_tenant_local():
    from datetime import datetime, timezone
    t = {"timezone": "Pacific/Auckland"}
    now = datetime(2026, 11, 20, 8, 57, tzinfo=timezone.utc)         # 21:57 NZDT
    s = on.distinct_subject(t, "Chat enquiry for X", "Channel: chat\nEmail: \nPhone: \n\nHow much?", now)
    assert s == "Chat enquiry for X: How much? (Fri 9:57pm)"
