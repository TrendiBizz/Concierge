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

from app import channel_authorization, db, enquiry_alerts as ea, outbox, owner_issues, owner_notifications as on

PORT = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
SCHEMA = Path(__file__).resolve().parent.parent / "app" / "schema.sql"


def _dsn(name="postgres"):
    # The full suite runs with TEST_DATABASE_URL (scripts/dev/test-db.sh); without this the whole file
    # skipped silently on the 55432 default (found 27 Nov 2026).
    base = os.environ.get("TEST_DATABASE_URL", "")
    if base:
        return base.rsplit("/", 1)[0] + "/" + name
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
            await conn.execute("TRUNCATE outbox, leads, conversations, tenants CASCADE")
            tid = await conn.fetchval(
                "INSERT INTO tenants(slug,name,public_key,notify_email,notify_phone,sms_enabled,sms_transport) "
                "VALUES('t','Harbour Dental','pk','owner@example.co.nz','+64210000001',true,'device') RETURNING id")
            tenant = dict(await conn.fetchrow("SELECT * FROM tenants WHERE id=$1", tid))
            monkeypatch.setattr(db, "pool", lambda: conn)
            monkeypatch.setattr(channel_authorization, "is_authorized", _true)
            monkeypatch.setattr(on, "spawn_push", lambda *a, **k: None)
            await scenario(conn, tenant)
        finally:
            await conn.close()
    asyncio.run(go())


async def _true(*a, **k):
    return True


async def _lead(conn, tenant, message="hello", channel="chat", **kw):
    return await conn.fetchval(
        "INSERT INTO leads(tenant_id,message,channel,name,email,phone) VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
        tenant["id"], message, channel, kw.get("name", ""), kw.get("email", ""), kw.get("phone", ""))


async def _conv(conn, tenant):
    return await conn.fetchval(
        "INSERT INTO conversations(tenant_id,session_id,channel) VALUES($1,$2,'chat') RETURNING id",
        tenant["id"], uuid.uuid4().hex)


async def _rows(conn, kind="owner_alert"):
    return await conn.fetch("SELECT * FROM outbox WHERE kind=$1 ORDER BY id", kind)


# ---- one alert per enquiry, worded per channel --------------------------------------------------

CASES = [  # channel, text, contact, subject lead-in, body phrase
    ("email", "Subject: quote\n\nCan you fit a deck in March?", {"email": "sam@gmail.com", "name": "Sam"},
     "Email enquiry for Harbour Dental from Sam", "Reply to them by email."),
    ("sms", "Hi do you do weekends", {"phone": "+64211234567"},
     "Text message for Harbour Dental from +64211234567", "Reply to them by text."),
    ("phone", "I need a quote for a deck.", {"phone": "+64211234567"},
     "Phone call for Harbour Dental from +64211234567", "Ring them back."),
    ("chat", "Enquirer: How much?\n\nConcierge: $250", {},
     "Web chat for Harbour Dental", "website chat"),
]


@pytest.mark.parametrize("channel,text,contact,subject,phrase", CASES)
def test_each_channel_gets_one_alert_with_its_own_template(dbname, monkeypatch, channel, text, contact, subject, phrase):
    async def scenario(conn, t):
        lead = await _lead(conn, t, text, channel, **contact)
        for _ in range(3):                                   # the same enquiry noticed three times
            await ea.notify(t, channel, text, lead_id=lead, contact=contact, connection=conn)
        rows = await _rows(conn)
        assert len(rows) == 1                                # ONE alert, ONE channel (email)
        assert rows[0]["channel"] == "email" and rows[0]["to_addr"] == "owner@example.co.nz"
        assert rows[0]["subject"].startswith(subject)
        assert phrase in rows[0]["body"]
        assert await conn.fetchval("SELECT count(*) FROM outbox WHERE channel='sms'") == 0   # no SMS copy
    run(dbname, monkeypatch, scenario)


def test_subjects_differ_per_channel_and_per_enquiry(dbname, monkeypatch):
    async def scenario(conn, t):
        for i, (channel, text, contact, *_rest) in enumerate(CASES * 2):
            text = f"#{i} " + text
            lead = await _lead(conn, t, text, channel, **contact)
            await ea.notify(t, channel, text, lead_id=lead, contact=contact, connection=conn)
        subjects = [r["subject"] for r in await _rows(conn)]
        assert len(subjects) == 8 and len(set(subjects)) == 8
    run(dbname, monkeypatch, scenario)


def test_thirty_chat_turns_make_exactly_one_alert_holding_the_whole_conversation(dbname, monkeypatch):
    async def scenario(conn, t):
        conv = await _conv(conn, t)
        lead = await _lead(conn, t)
        await conn.execute("UPDATE leads SET conversation_id=$1", conv)
        for turn in range(30):
            await ea.notify(t, "chat", f"Enquirer: question {turn}", lead_id=lead, connection=conn)
        rows = await _rows(conn)
        assert len(rows) == 1 and "question 29" in rows[0]["body"]
        assert rows[0]["send_at"] > rows[0]["created_at"]                  # debounced while it merges
    run(dbname, monkeypatch, scenario)


def test_enquiry_capture_and_dialogue_for_one_conversation_are_one_alert(dbname, monkeypatch):
    """Prod 21 Nov: two emails 7 s apart for one conversation. Lead found by lead id OR by conversation id."""
    async def scenario(conn, t):
        conv = await _conv(conn, t)
        lead = await _lead(conn, t, "How much?")
        await conn.execute("UPDATE leads SET conversation_id=$1", conv)
        await ea.notify(t, "chat", "How much?", lead_id=lead, conversation_id=conv, connection=conn)
        await ea.notify(t, "chat", "Enquirer: How much?\n\nConcierge: $250", conversation_id=conv, connection=conn)
        rows = await _rows(conn)
        assert len(rows) == 1 and "$250" in rows[0]["body"]
    run(dbname, monkeypatch, scenario)


def test_after_the_alert_is_sent_later_turns_make_no_second_alert(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t)
        await ea.notify(t, "chat", "Enquirer: first", lead_id=lead, connection=conn)
        await conn.execute("UPDATE outbox SET status='sent', sent_at=now()")
        await ea.notify(t, "chat", "Enquirer: first\n\nEnquirer: second", lead_id=lead, connection=conn)
        assert len(await _rows(conn)) == 1
        await conn.execute("UPDATE outbox SET created_at = now() - interval '25 hours'")   # a day later: new enquiry
        await ea.notify(t, "chat", "Enquirer: back again", lead_id=lead, connection=conn)
        assert len(await _rows(conn)) == 2
    run(dbname, monkeypatch, scenario)


def test_different_conversations_are_different_enquiries(dbname, monkeypatch):
    async def scenario(conn, t):
        a, b = await _lead(conn, t, "How much?"), await _lead(conn, t, "Yearly plan?")
        await ea.notify(t, "chat", "How much?", lead_id=a, connection=conn)
        await ea.notify(t, "chat", "Yearly plan?", lead_id=b, connection=conn)
        assert len(await _rows(conn)) == 2
    run(dbname, monkeypatch, scenario)


def test_a_phone_calls_start_and_end_are_one_alert_and_a_silent_call_still_alerts(dbname, monkeypatch):
    async def scenario(conn, t):
        conv = await _conv(conn, t)
        lead = await _lead(conn, t, "Inbound telephone enquiry", "phone", phone="+64211234567")
        await conn.execute("UPDATE leads SET conversation_id=$1", conv)
        await ea.notify(t, "phone", "Inbound telephone enquiry", lead_id=lead, connection=conn, hold_seconds=300)
        held = await conn.fetchval("SELECT extract(epoch FROM send_at - now()) FROM outbox")
        assert 250 < held <= 300                                          # waits for the call to end
        await ea.notify(t, "phone", "I need a quote for a deck.", lead_id=lead, conversation_id=conv,
                        connection=conn, finalize=True)
        rows = await _rows(conn)
        assert len(rows) == 1 and "quote for a deck" in rows[0]["body"]
        assert await conn.fetchval("SELECT extract(epoch FROM send_at - now()) FROM outbox") <= 45
        await conn.execute("DELETE FROM outbox")                         # a call with no message: still alerts
        await ea.notify(t, "phone", "Inbound telephone enquiry", lead_id=lead, connection=conn, hold_seconds=300)
        await conn.execute("UPDATE outbox SET send_at = now()")
        assert await conn.fetchval("SELECT count(*) FROM outbox WHERE status='pending' AND send_at <= now()") == 1
    run(dbname, monkeypatch, scenario)


# ---- genuine vs not -----------------------------------------------------------------------------

@pytest.mark.parametrize("channel,text,contact", [
    ("email", "Listing inquiry\n\nSomeone viewed your listing", {"email": "care@yellow.co.nz"}),
    ("email", "Thank you for contacting us. Your ticket number is 4411.", {"email": "help@somevendor.com"}),
    ("email", "Your code", {"email": "noreply@tiktok.com"}),
    ("sms", "Your verification code is 482913", {"phone": "+64270000000"}),
    ("email", "Hello", {"email": "x@y.com"}),       # flagged automated by the ingest layer
])
def test_vendor_otp_and_robot_messages_make_no_owner_alert(dbname, monkeypatch, channel, text, contact):
    async def scenario(conn, t):
        lead = await _lead(conn, t, text, channel, **contact)
        flagged = text == "Hello"
        assert await ea.notify(t, channel, text, lead_id=lead, contact=contact, connection=conn, automated=flagged) is None
        assert await conn.fetchval("SELECT count(*) FROM outbox") == 0
    run(dbname, monkeypatch, scenario)


def test_a_real_customer_email_is_not_mistaken_for_a_vendor(dbname, monkeypatch):
    async def scenario(conn, t):
        lead = await _lead(conn, t, channel="email", email="sam@gmail.com")
        assert await ea.notify(t, "email", "Hi, can you quote a deck?", lead_id=lead,
                               contact={"email": "sam@gmail.com"}, connection=conn)
    run(dbname, monkeypatch, scenario)


# ---- delivery channel chosen once ---------------------------------------------------------------

def test_email_is_primary_and_sms_is_only_used_when_there_is_no_email_and_it_is_reliable(dbname, monkeypatch):
    async def scenario(conn, t):
        assert await on.delivery_route(conn, t) == ("email", "owner@example.co.nz")
        no_email = {**t, "notify_email": ""}
        assert await on.delivery_route(conn, no_email) == ("sms", "+64210000001")
        for i in range(3):                                                # three unconfirmed texts: not reliable
            await conn.execute(
                "INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,last_error) VALUES"
                "($1,'owner_alert','sms','+64210000001','b','failed','Phone did not confirm send')", t["id"])
        assert await on.delivery_route(conn, no_email) is None
        assert await on.delivery_route(conn, t) == ("email", "owner@example.co.nz")
    run(dbname, monkeypatch, scenario)


def test_one_off_owner_notices_use_one_channel_and_dedupe(dbname, monkeypatch):
    async def scenario(conn, t):
        for _ in range(2):
            assert await on.queue(t, "Payment received", "Paid", "pay:1", connection=conn) == ["email"]
        assert len(await _rows(conn)) == 1
    run(dbname, monkeypatch, scenario)


def test_there_is_no_sms_to_email_fallback_any_more():
    from app import channel_health
    assert not hasattr(channel_health, "escalate_failed_owner_alerts") and not hasattr(channel_health, "_fallback")


# ---- issue notices ------------------------------------------------------------------------------

def test_failed_owner_sms_makes_one_action_needed_email_and_never_a_copy(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        no_email = {**t, "notify_email": ""}
        await conn.execute("UPDATE tenants SET notify_email=''")
        lead = await _lead(conn, t, "Hi", "sms", phone="+64211234567")
        await ea.notify(no_email, "sms", "Secret customer words", lead_id=lead, contact={"phone": "+64211234567"}, connection=conn)
        await conn.execute("UPDATE outbox SET status='failed', last_error='Phone did not confirm send'")
        await conn.execute("UPDATE tenants SET notify_email='owner@example.co.nz'")
        for _ in range(3):
            await owner_issues.sweep_undelivered()
        issues = await _rows(conn, "owner_issue")
        assert len(issues) == 1 and issues[0]["channel"] == "email"
        assert issues[0]["subject"].startswith("ACTION NEEDED")
        assert "Secret customer words" not in issues[0]["body"] and "did not confirm" in issues[0]["body"]
        assert len(await _rows(conn)) == 1                                # still just the one (failed) alert
    run(dbname, monkeypatch, scenario)


def test_failed_email_alert_issue_goes_by_sms_only_if_reliable_else_logged(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        lead = await _lead(conn, t, "Hi", "email", email="sam@gmail.com")
        await ea.notify(t, "email", "Hi there", lead_id=lead, contact={"email": "sam@gmail.com"}, connection=conn)
        await conn.execute("UPDATE outbox SET status='failed', last_error='blocklisted'")
        await owner_issues.sweep_undelivered(); await owner_issues.sweep_undelivered()
        issues = await _rows(conn, "owner_issue")
        assert [i["channel"] for i in issues] == ["sms"] and "Hi there" not in issues[0]["body"]
    run(dbname, monkeypatch, scenario)


def test_unanswered_enquiry_makes_one_notice_only_for_genuine_enquiries(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        monkeypatch.setattr(owner_issues.outbox, "next_allowed_send", lambda tz, when: when)
        real = await _lead(conn, t, "Quote please", "email", email="sam@gmail.com", name="Sam")
        vendor = await _lead(conn, t, "Listing inquiry", "email", email="care@yellow.co.nz")
        await ea.notify(t, "email", "Quote please", lead_id=real, contact={"email": "sam@gmail.com"}, connection=conn)
        await ea.notify(t, "email", "Listing inquiry", lead_id=vendor, contact={"email": "care@yellow.co.nz"}, connection=conn)
        await conn.execute("UPDATE leads SET created_at = now() - interval '3 hours'")
        assert await owner_issues.sweep_unanswered() == 1
        assert await owner_issues.sweep_unanswered() == 0                 # deduped per enquiry + issue type
        issues = await _rows(conn, "owner_issue")
        assert len(issues) == 1 and "Sam" in issues[0]["subject"] and "Quote please" not in issues[0]["body"]
        await conn.execute("UPDATE leads SET status='contacted'")
        await conn.execute("DELETE FROM outbox WHERE kind='owner_issue'")
        assert await owner_issues.sweep_unanswered() == 0                 # replied to: nothing to chase
    run(dbname, monkeypatch, scenario)


def test_unanswered_notice_is_not_raised_before_the_threshold(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        lead = await _lead(conn, t, "Hi", "sms", phone="+64211234567")
        await ea.notify(t, "sms", "Hi", lead_id=lead, contact={"phone": "+64211234567"}, connection=conn)
        await conn.execute("UPDATE leads SET created_at = now() - interval '30 minutes'")
        assert await owner_issues.sweep_unanswered() == 0
    run(dbname, monkeypatch, scenario)


def test_failed_reply_to_customer_makes_one_notice(dbname, monkeypatch):
    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        lead = await _lead(conn, t, "Hi", "email", email="sam@gmail.com", name="Sam")
        await conn.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,last_error,lead_id) VALUES"
            "($1,'email_secretary_reply','email','sam@gmail.com','reply','failed','mailbox full',$2)", t["id"], lead)
        assert await owner_issues.sweep_reply_failed() == 1
        assert await owner_issues.sweep_reply_failed() == 0
        issues = await _rows(conn, "owner_issue")
        assert len(issues) == 1 and "mailbox full" in issues[0]["body"] and issues[0]["subject"].startswith("ACTION NEEDED")
    run(dbname, monkeypatch, scenario)


def test_subject_is_tenant_local_time():
    from datetime import datetime, timezone
    now = datetime(2026, 11, 20, 8, 57, tzinfo=timezone.utc)         # 21:57 NZDT
    s = ea.subject_for({"name": "X", "timezone": "Pacific/Auckland"}, "chat", "", "Enquirer: How much?", now)
    assert s == "Web chat for X: How much? (Fri 9:57pm)"


# ---- threads the owner runs from their own mailbox (27 Nov 2026, Ruben) ---------------------------

async def _draft(conn, tenant, sender, message_id):
    await conn.execute(
        "INSERT INTO email_drafts(tenant_id,sender,subject,inbound_body,reply_body,message_id_hdr) "
        "VALUES($1,$2,'Re: link swap','body','REVIEW',$3)", tenant["id"], sender, message_id)


def test_reply_to_the_owners_own_email_is_not_chased(dbname, monkeypatch):
    """Ruben answered Jo's Gmail outreach twice; Concierge saw only his mail and nagged 'no reply yet'."""
    from app import owner_threads

    async def scenario(conn, t):
        monkeypatch.setattr(owner_issues.db, "pool", lambda: conn)
        monkeypatch.setattr(owner_threads.db, "pool", lambda: conn)
        await conn.execute("DELETE FROM email_drafts")
        first = await _lead(conn, t, "Re: link swap: placed your link", "email", email="ruben@ringly.io", name="Ruben")
        await conn.execute("UPDATE leads SET created_at = now() - interval '2 days'")
        await _draft(conn, t, "ruben@ringly.io", "<r1@ringly.io>")
        second = await _lead(conn, t, "Re: link swap: thanks Jo, link live", "email", email="ruben@ringly.io", name="Ruben")
        await _draft(conn, t, "ruben@ringly.io", "<r2@ringly.io>")
        await ea.notify(t, "email", "thanks Jo", lead_id=second, contact={"email": "ruben@ringly.io"}, connection=conn)
        lead = {"id": second}
        # Parent is Jo's Gmail message: not one of Ruben's, and Concierge never emailed him.
        assert await owner_threads.note(t["id"], lead, "Ruben@Ringly.io", {"in_reply_to": "<jo@mail.gmail.com>"})
        assert await conn.fetchval("SELECT status FROM leads WHERE id=$1", first) == "contacted"
        assert await conn.fetchval("SELECT owner_thread FROM leads WHERE id=$1", second) is True
        await conn.execute("UPDATE leads SET created_at = now() - interval '3 hours' WHERE id=$1", second)
        assert await owner_issues.sweep_unanswered() == 0
        assert await _rows(conn, "owner_issue") == []
    run(dbname, monkeypatch, scenario)


def test_owner_thread_needs_evidence(dbname, monkeypatch):
    from app import owner_threads

    async def scenario(conn, t):
        monkeypatch.setattr(owner_threads.db, "pool", lambda: conn)
        await conn.execute("DELETE FROM email_drafts")
        lead = await _lead(conn, t, "Quote please", "email", email="sam@gmail.com", name="Sam")
        await _draft(conn, t, "sam@gmail.com", "<s1@gmail.com>")
        assert not await owner_threads.note(t["id"], {"id": lead}, "sam@gmail.com", {})            # not a reply
        assert not await owner_threads.note(t["id"], {"id": lead}, "sam@gmail.com",
                                            {"in_reply_to": "<s1@gmail.com>"})                    # follow-up to own mail
        await conn.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,lead_id) VALUES"
            "($1,'inbound_ack','email','sam@gmail.com','got it','sent',$2)", t["id"], lead)
        assert not await owner_threads.note(t["id"], {"id": lead}, "sam@gmail.com",
                                            {"in_reply_to": "<x@trendi>"})                        # may be our ack
        assert await conn.fetchval("SELECT owner_thread FROM leads WHERE id=$1", lead) is False
    run(dbname, monkeypatch, scenario)


def test_unanswered_notice_uses_an_before_email():
    import inspect
    assert '"An" if kind[:1] in "aeiou"' in inspect.getsource(owner_issues.sweep_unanswered)
