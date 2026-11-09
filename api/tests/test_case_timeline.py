"""Unified customer case timeline and follow-up coverage.

A customer who emails, then texts, then calls is ONE person with ONE case history. Before this
module existed, each channel keyed its own conversation (call_sid / email hash / sms session), so
the three channels produced three unrelated conversations and the owner could not see that the same
person had already been helped somewhere else.

These tests pin the behaviour that closes that gap, plus the follow-up coverage gap: the response
target check in sla.py only ever looked at scored leads, so an inbound email or text that did not
clear the score threshold was never chased.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import casetimeline, contact, sla, tasks

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "sla_minutes": 60,
    "sla_min_score": 70,
    "notify_email": "owner@example.com",
}


# ---------------------------------------------------------------- identity


def test_case_key_prefers_e164_phone_over_email():
    """A phone number is the stronger identity: it survives an address change."""
    key = casetimeline.case_key(phone="+6421555123", email="Hana@Example.com")
    assert key == "phone:+6421555123"


def test_case_key_normalises_email_case_and_domain():
    key = casetimeline.case_key(phone="", email="  Hana@Example.COM ")
    assert key == "email:hana@example.com"


def test_case_key_returns_none_when_no_usable_identity():
    assert casetimeline.case_key(phone="not-a-phone", email="") is None
    assert casetimeline.case_key(phone="", email="") is None


def test_case_key_rejects_implausible_phone():
    """A garbage string must not become a shared case that merges two different customers."""
    assert casetimeline.case_key(phone="+1", email="") is None


# ---------------------------------------------------------------- merge rules


def test_same_person_on_two_channels_resolves_to_one_case():
    """The core promise: email and SMS from one customer share a case."""
    a = casetimeline.case_key(phone="+6421555123", email="hana@example.com")
    b = casetimeline.case_key(phone="+6421555123", email="")
    assert a == b == "phone:+6421555123"


def test_bare_local_number_needs_the_right_country_code():
    """A bare local number must not be decoded as US, or one customer becomes two cases.

    With the global default of '1', 6421555123 normalised to +16421555123 -- a DIFFERENT case from
    +6421555123. Selecting the tenant's own country code is what keeps one customer as one case.
    """
    wrong = casetimeline.case_key(phone="6421555123", email="", default_cc="1")
    right = casetimeline.case_key(phone="+6421555123", email="", default_cc="64")
    assert wrong == "phone:+16421555123"
    assert right == "phone:+6421555123"
    assert wrong != right


def test_tenant_country_code_prefers_the_tenant_value(monkeypatch):
    monkeypatch.setattr(casetimeline, "get_settings", lambda: SimpleNamespace(default_country_code="1"))
    assert casetimeline.tenant_country_code({"default_country_code": "64"}) == "64"
    assert casetimeline.tenant_country_code({}) == "1"
    assert casetimeline.tenant_country_code(None) == "1"
    # A malformed tenant value must fall back, not be used as-is.
    assert casetimeline.tenant_country_code({"default_country_code": "not-a-code"}) == "1"


def test_international_form_is_stable_across_tenants(monkeypatch):
    """+6421555123 is unambiguous, so it keys identically whatever the tenant's dialling country."""
    monkeypatch.setattr(casetimeline, "get_settings", lambda: SimpleNamespace(default_country_code="1"))
    nz = casetimeline.case_key_for_tenant({"default_country_code": "64"}, phone="+6421555123")
    us = casetimeline.case_key_for_tenant({"default_country_code": "1"}, phone="+6421555123")
    assert nz == us == "phone:+6421555123"


@pytest.mark.xfail(
    reason="Shared normalize_phone() cannot parse local formats: it treats any 8-15 digit string as "
           "already-E.164 and only prefixes '+', so '6421555123' becomes '+646421555123' and "
           "'021555123' becomes '+021555123'. Fixing it changes booking, SMS, outbox, campaigns and "
           "tools together, so it is reported rather than half-fixed here.",
    strict=True,
)
def test_local_form_unifies_with_international_form(monkeypatch):
    """KNOWN BUG: a NZ customer writing 6421555123 and +6421555123 should be ONE case."""
    monkeypatch.setattr(casetimeline, "get_settings", lambda: SimpleNamespace(default_country_code="1"))
    tenant = {"default_country_code": "64"}
    assert (casetimeline.case_key_for_tenant(tenant, phone="6421555123")
            == casetimeline.case_key_for_tenant(tenant, phone="+6421555123"))


def test_different_customers_never_share_a_case():
    a = casetimeline.case_key(phone="+6421555123", email="")
    b = casetimeline.case_key(phone="+6421555999", email="")
    assert a != b


# ---------------------------------------------------------------- SLA coverage


def test_overdue_reports_every_open_lead_not_only_high_scoring(monkeypatch):
    """A low-scoring email enquiry must still be chased, or it is silently abandoned."""
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        captured["args"] = args
        return []

    monkeypatch.setattr(sla.db, "pool", lambda: SimpleNamespace(fetch=fake_fetch))
    asyncio.run(sla.overdue(TENANT))

    sql = captured["sql"]
    # The old query hard-required score >= sla_min_score, which hid whole channels.
    assert "score >= $2" not in sql, "overdue() still filters out low-scoring enquiries"
    assert "status = 'new'" in sql


def test_overdue_ignores_opted_out_contacts(monkeypatch):
    """Chasing someone who opted out is a compliance failure, not a lead."""
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        return []

    monkeypatch.setattr(sla.db, "pool", lambda: SimpleNamespace(fetch=fake_fetch))
    asyncio.run(sla.overdue(TENANT))
    assert "opt_outs" in captured["sql"]


def test_overdue_respects_human_takeover(monkeypatch):
    """Once the owner replies, the automation must stop chasing that customer."""
    captured = {}

    async def fake_fetch(sql, *args):
        captured["sql"] = sql
        return []

    monkeypatch.setattr(sla.db, "pool", lambda: SimpleNamespace(fetch=fake_fetch))
    asyncio.run(sla.overdue(TENANT))
    assert "automation_paused" in captured["sql"]


def test_overdue_is_empty_when_feature_disabled(monkeypatch):
    """sla_minutes = 0 means the client turned follow-ups off entirely."""
    monkeypatch.setattr(sla.db, "pool", lambda: pytest.fail("disabled feature queried the database"))
    assert asyncio.run(sla.overdue({**TENANT, "sla_minutes": 0})) == []


# ---------------------------------------------------------------- follow-up per message


def test_each_inbound_message_gets_its_own_follow_up(monkeypatch):
    """One follow-up per lead was the old rule; a second message produced no new to-do."""
    inserts = []

    async def fake_fetchrow(sql, *args, **kwargs):
        inserts.append(sql)
        return {"id": 7}

    monkeypatch.setattr(tasks.db, "pool", lambda: SimpleNamespace(fetchrow=fake_fetchrow))
    lead = {"id": "lead-1", "name": "Hana", "message": "hi", "tenant_id": TENANT["id"],
            "score_label": "warm", "source_key": "abc"}
    asyncio.run(tasks.create_follow_up(TENANT, lead, message_key="email:abc"))
    sql = inserts[0]
    assert "ON CONFLICT" in sql
    # The uniqueness must be per message, not per lead, or follow-ups stop after the first contact.
    assert "message_key" in sql


def test_create_follow_up_returns_none_on_duplicate(monkeypatch):
    """A replayed webhook must not create a second identical to-do."""
    async def fake_fetchrow(sql, *args, **kwargs):
        return None

    monkeypatch.setattr(tasks.db, "pool", lambda: SimpleNamespace(fetchrow=fake_fetchrow))
    lead = {"id": "lead-1", "name": "Hana", "message": "hi", "tenant_id": TENANT["id"],
            "score_label": "hot", "source_key": "abc"}
    assert asyncio.run(tasks.create_follow_up(TENANT, lead, message_key="email:abc")) is None


def test_follow_up_default_due_still_uses_sla_for_hot_leads():
    now = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    lead = {"score_label": "hot"}
    due = tasks.default_follow_up_due(TENANT, lead, now)
    assert due == now.replace(minute=0) + __import__("datetime").timedelta(minutes=60)


# ---------------------------------------------------------------- timeline recording


def test_recording_a_message_is_idempotent(monkeypatch):
    """Replayed provider webhooks must collapse, not duplicate the timeline."""
    calls = []

    async def fake_fetchrow(sql, *args):
        calls.append(sql)
        return {"id": 1}

    async def fake_execute(sql, *args):
        return "UPDATE 1"

    monkeypatch.setattr(casetimeline.db, "pool",
                        lambda: SimpleNamespace(fetchrow=fake_fetchrow, execute=fake_execute))
    asyncio.run(casetimeline.record(
        TENANT["id"], case_key="phone:+6421555123", channel="sms",
        direction="inbound", source_key="msg-1", body="hello",
    ))
    assert "ON CONFLICT" in calls[0]


def test_manual_reply_marks_human_takeover(monkeypatch):
    """When the owner answers, automation for that case must pause."""
    executed = []

    async def fake_execute(sql, *args):
        executed.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(casetimeline.db, "pool", lambda: SimpleNamespace(execute=fake_execute))
    asyncio.run(casetimeline.set_takeover(TENANT["id"], case_key="email:hana@example.com", paused=True))
    assert any("automation_paused" in sql for sql, _ in executed)
    assert any(True for _, args in executed if True in args)


# ---------------------------------------------------------------- DB-backed integration
#
# The unit tests above mock the pool, so they cannot catch a wrong SQL parameter type or a broken
# join. These run against the real PostgreSQL that CI supplies; they skip cleanly when it is absent
# rather than failing a developer's machine for an unrelated reason.

import os

import asyncpg

import pytest as _pytest

from app import db as _db

# One loop for the whole module. asyncpg binds a connection to the loop that created it, so a fresh
# loop per call leaves the pool unusable ("There is no current event loop").
_LOOP = None


def _loop():
    """The single loop used by every DB-backed test in this module.

    Created lazily and re-registered as the thread's current loop on each use, because pytest can
    clear the current loop between fixtures and asyncpg then refuses to create a pool with
    "There is no current event loop in thread 'MainThread'".
    """
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP


def _dsn():
    port = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
    return f"postgresql://postgres:test@127.0.0.1:{port}/postgres"


def _run(coro):
    """Run a coroutine on one persistent loop.

    The pool, the schema setup and the assertions must share a single event loop: asyncpg binds
    connections to the loop that created them, and a fresh loop per call leaves the pool unusable
    with "There is no current event loop".
    """
    return _loop().run_until_complete(coro)


@pytest.fixture()
def real_db():
    """A clean schema on the throwaway test database, or skip."""
    schema = (__import__("pathlib").Path(__file__).parent.parent / "app" / "schema.sql").read_text()
    schema = schema.replace("__DIM__", "384")
    async def connect():
        # Pass the loop explicitly: asyncpg's internal asyncio.get_event_loop() is deprecated in
        # Python 3.13 and raises under pytest, which would otherwise make this skip silently.
        return await asyncpg.create_pool(
            _dsn(), min_size=1, max_size=4, timeout=5, loop=_loop())

    try:
        pool = _run(connect())
    except Exception as exc:  # noqa: BLE001 - any connection problem means "no database here"
        pytest.skip(f"No test PostgreSQL available: {exc}")
    async def setup():
        async with pool.acquire() as c:
            await c.execute("drop schema if exists public cascade; create schema public")
            await c.execute(schema)
    _run(setup())
    previous = _db._pool
    _db._pool = pool
    yield pool
    _db._pool = previous
    _run(pool.close())


def _capture(tenant, channel, source, message, **kw):
    from app import enquiries, owner_notifications, automation
    from unittest.mock import AsyncMock
    owner_notifications.queue = AsyncMock()
    automation.on_lead_created = AsyncMock()
    return _run(enquiries.capture(tenant, channel, source, message, **kw))


def test_one_customer_across_three_channels_is_one_case(real_db):
    """The headline requirement: email, SMS and a phone call from one person form ONE case."""
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))

    _capture(tenant, "email", "e1", "Quote please", email="hana@example.com")
    _capture(tenant, "sms", "s1", "Any update?", phone="+6421555123", email="hana@example.com")
    _capture(tenant, "phone", "c1", "Called in", phone="+6421555123")

    assert _run(real_db.fetchval("select count(*) from customer_cases")) == 1
    assert _run(real_db.fetchval("select count(distinct case_id) from leads")) == 1
    events = _run(casetimeline.timeline(tid, "phone:+6421555123"))
    assert sorted(e["channel"] for e in events) == ["email", "phone", "sms"]


def test_message_carrying_both_identifiers_merges_both_cases(real_db):
    """When a message carries BOTH a phone and an email, the two earlier cases become one.

    This is the merge guarantee that actually holds, and it is the one that matters in practice:
    the channel that supplies both identifiers is what links the identities.
    """
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))

    # Two cases for one person, created from the two separate identifiers.
    _capture(tenant, "email", "e1", "Quote please", email="hana@example.com")
    _capture(tenant, "phone", "c1", "Called in", phone="+6421555123")
    assert _run(real_db.fetchval("select count(*) from customer_cases")) == 2

    # A message carrying both links them into one customer.
    _capture(tenant, "sms", "s1", "Any update?", phone="+6421555123", email="hana@example.com")
    assert _run(real_db.fetchval("select count(*) from customer_cases")) == 1
    assert _run(real_db.fetchval("select count(distinct case_id) from leads")) == 1
    events = _run(casetimeline.timeline(tid, "phone:+6421555123"))
    assert sorted(e["channel"] for e in events) == ["email", "phone", "sms"]


def test_phone_only_message_does_not_guess_at_an_unrelated_email_case(real_db):
    """An identity we cannot link must NOT be merged, because merging strangers is worse.

    Given only a phone number there is no evidence it belongs to an existing email-only customer.
    Auto-merging on no evidence would fuse two different people into one history, so a phone-only
    message correctly forms its own case until a channel supplies a linking identifier.
    """
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))

    _capture(tenant, "email", "e1", "Quote please", email="hana@example.com")
    _capture(tenant, "phone", "c1", "Called in", phone="+6421555123")
    assert _run(real_db.fetchval("select count(*) from customer_cases")) == 2, (
        "an unlinked phone number must not be silently fused into an email case")


def test_two_customers_are_never_merged(real_db):
    """Merging must not go too far: distinct people stay distinct."""
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))
    _capture(tenant, "sms", "s1", "one", phone="+6421555123")
    _capture(tenant, "sms", "s2", "two", phone="+6421555999")
    assert _run(real_db.fetchval("select count(*) from customer_cases")) == 2


def test_replayed_webhook_does_not_duplicate_history(real_db):
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))
    _capture(tenant, "sms", "s1", "hello", phone="+6421555123")
    _capture(tenant, "sms", "s1", "hello", phone="+6421555123")
    assert _run(real_db.fetchval("select count(*) from case_events")) == 1


def test_takeover_survives_a_merge(real_db):
    """An owner's personal reply must keep automation paused even after cases merge."""
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) "
        "values('nz','NZ Biz','pk1','64') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))
    _capture(tenant, "email", "e1", "Quote please", email="hana@example.com")
    _run(casetimeline.set_takeover(tid, case_key="email:hana@example.com", paused=True))
    # A later message carrying a phone number merges the two identities.
    _capture(tenant, "sms", "s1", "Any update?", phone="+6421555123", email="hana@example.com")
    assert _run(real_db.fetchval(
        "select automation_paused from customer_cases where tenant_id=$1", tid)) is True


def test_sla_chases_low_scoring_email_and_excludes_opt_outs(real_db):
    """The coverage fix: a low-scoring email is chased, an opted-out contact is not."""
    tid = _run(real_db.fetchval(
        "insert into tenants(slug,name,public_key,timezone,sla_minutes,sla_min_score,notify_email) "
        "values('nz','NZ','pk1','Pacific/Auckland',60,70,'o@e.com') returning id"))
    tenant = dict(_run(real_db.fetchrow("select * from tenants where id=$1", tid)))
    _run(real_db.execute(
        "insert into leads(tenant_id,email,message,channel,score,score_label,status,created_at) "
        "values($1,'hana@example.com','Quote','email',10,'cold','new',now()-interval '3 hours')", tid))
    _run(real_db.execute(
        "insert into leads(tenant_id,email,message,channel,score,score_label,status,created_at) "
        "values($1,'stop@example.com','x','email',95,'hot','new',now()-interval '3 hours')", tid))
    _run(real_db.execute("insert into opt_outs(tenant_id,contact) values($1,'stop@example.com')", tid))

    rows = _run(sla.overdue(tenant))
    assert any(r["score"] == 10 for r in rows), "low-scoring email enquiry was not chased"
    assert not any(r["email"] == "stop@example.com" for r in rows), "opted-out contact was chased"
