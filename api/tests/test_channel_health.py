"""Owner alerts must not be silently lost when one channel fails (2026-11-12 audit)."""
import asyncio
from datetime import timedelta

from app import channel_health


class FakePool:
    def __init__(self, rows=None, row=None, fb_recent=0):
        self.rows = rows or []
        self.row = row
        self.fb_recent = fb_recent
        self.fetch_sql = ""
        self.fetch_args = ()

    async def fetchval(self, sql, *args):
        return self.fb_recent

    async def fetch(self, sql, *args):
        self.fetch_sql = " ".join(sql.split())
        self.fetch_args = args
        return self.rows

    async def fetchrow(self, sql, *args):
        return self.row


def _row(channel, **over):
    base = {"id": 7, "tenant_id": "t1", "channel": channel, "to_addr": "x", "subject": "New enquiry",
            "body": "Jo called about a deck.", "notify_phone": "+6421824305",
            "notify_email": "owner@example.co.nz"}
    base.update(over)
    return base


def _run_escalation(monkeypatch, rows):
    queued = []

    async def fake_enqueue(tenant_id, kind, channel, to_addr, body, subject="", dedupe_key=None, **kw):
        queued.append({"channel": channel, "to": to_addr, "body": body, "kind": kind, "dedupe": dedupe_key})
        return True

    pool = FakePool(rows=rows)
    monkeypatch.setattr(channel_health.db, "pool", lambda: pool)
    monkeypatch.setattr(channel_health.outbox, "enqueue", fake_enqueue)
    return asyncio.run(channel_health.escalate_failed_owner_alerts()), queued, pool


def test_failed_sms_alert_is_resent_by_email(monkeypatch):
    count, queued, _ = _run_escalation(monkeypatch, [_row("sms", to_addr="+6421824305")])
    assert count == 1
    assert queued[0]["channel"] == "email" and queued[0]["to"] == "owner@example.co.nz"
    assert queued[0]["kind"] == "owner_alert"
    assert queued[0]["dedupe"] == "fb:7:email"
    assert "could not be confirmed" in queued[0]["body"]
    assert "Jo called about a deck." in queued[0]["body"]


def test_refused_email_alert_is_resent_by_sms_and_trimmed(monkeypatch):
    long_body = "A" * 900
    count, queued, _ = _run_escalation(monkeypatch, [_row("email", to_addr="owner@example.co.nz", body=long_body)])
    assert count == 1
    assert queued[0]["channel"] == "sms" and queued[0]["to"] == "+6421824305"
    assert len(queued[0]["body"]) == 300
    assert queued[0]["dedupe"] == "fb:7:sms"


def test_no_fallback_when_the_other_channel_has_no_target(monkeypatch):
    count, queued, _ = _run_escalation(monkeypatch, [_row("sms", notify_email="")])
    assert count == 0 and queued == []


def test_no_fallback_to_the_same_address_that_just_failed(monkeypatch):
    count, queued, _ = _run_escalation(
        monkeypatch, [_row("sms", to_addr="owner@example.co.nz", notify_email="owner@example.co.nz")])
    assert count == 0 and queued == []


def test_already_escalated_alert_is_not_queued_twice(monkeypatch):
    async def duplicate(*a, **k):
        return False  # outbox.enqueue returns False when the dedupe key exists

    pool = FakePool(rows=[_row("sms")])
    monkeypatch.setattr(channel_health.db, "pool", lambda: pool)
    monkeypatch.setattr(channel_health.outbox, "enqueue", duplicate)
    assert asyncio.run(channel_health.escalate_failed_owner_alerts()) == 0


def test_sweep_only_reads_recent_failed_non_fallback_owner_alerts(monkeypatch):
    _, _, pool = _run_escalation(monkeypatch, [])
    sql = pool.fetch_sql
    assert "o.kind = 'owner_alert'" in sql
    assert "NOT LIKE 'fb:%'" in sql  # a fallback is never escalated again: no loops
    assert "make_interval(hours =>" in sql


def test_enqueue_errors_do_not_stop_the_sweep(monkeypatch):
    calls = []

    async def flaky(tenant_id, kind, channel, to_addr, body, subject="", dedupe_key=None, **kw):
        calls.append(dedupe_key)
        if len(calls) == 1:
            raise RuntimeError("db hiccup")
        return True

    pool = FakePool(rows=[_row("sms", id=1), _row("sms", id=2)])
    monkeypatch.setattr(channel_health.db, "pool", lambda: pool)
    monkeypatch.setattr(channel_health.outbox, "enqueue", flaky)
    assert asyncio.run(channel_health.escalate_failed_owner_alerts()) == 1
    assert calls == ["fb:1:email", "fb:2:email"]


def _device(**over):
    base = {"enabled": True, "last_seen": "seen", "verified_at": "v", "inbound_verified_at": None,
            "silent_for": timedelta(minutes=1)}
    base.update(over)
    return base


def _health(monkeypatch, fn, row):
    monkeypatch.setattr(channel_health.db, "pool", lambda: FakePool(row=row))
    return asyncio.run(fn("t1"))


def test_sms_device_states(monkeypatch):
    assert _health(monkeypatch, channel_health.sms_device_health, None)["state"] == "not_configured"
    assert _health(monkeypatch, channel_health.sms_device_health, _device(last_seen=None))["state"] == "offline"
    stale = _device(silent_for=timedelta(hours=45))
    assert _health(monkeypatch, channel_health.sms_device_health, stale)["state"] == "offline"
    assert _health(monkeypatch, channel_health.sms_device_health, _device(verified_at=None))["state"] == "unverified"
    online = _health(monkeypatch, channel_health.sms_device_health, _device())
    assert online["state"] == "online" and online["ok"] is True


def test_email_and_voice_health(monkeypatch):
    assert _health(monkeypatch, channel_health.email_health, {"bad": 70, "good": 0})["state"] == "refused"
    assert _health(monkeypatch, channel_health.email_health, {"bad": 1, "good": 5})["ok"] is True
    assert _health(monkeypatch, channel_health.voice_health, {"bad": 3, "good": 0})["state"] == "failing"
    assert _health(monkeypatch, channel_health.voice_health, {"bad": 0, "good": 0})["state"] == "untested"
    assert _health(monkeypatch, channel_health.voice_health, {"bad": 1, "good": 2})["ok"] is True


def _capped(monkeypatch, rows, fb_recent):
    queued = []

    async def enqueue(tenant_id, kind, channel, to_addr, body, subject="", dedupe_key=None, **kw):
        queued.append(dedupe_key)
        return True

    pool = FakePool(rows=rows, fb_recent=fb_recent)
    monkeypatch.setattr(channel_health.db, "pool", lambda: pool)
    monkeypatch.setattr(channel_health.outbox, "enqueue", enqueue)
    return asyncio.run(channel_health.escalate_failed_owner_alerts()), queued, pool


def test_escalation_stops_at_the_hourly_cap_per_business(monkeypatch):
    rows = [_row("sms", id=i) for i in range(1, 8)]
    count, queued, _ = _capped(monkeypatch, rows, fb_recent=0)
    assert channel_health.MAX_ESCALATIONS_PER_TENANT_HOUR == 3
    assert count == 3 and len(queued) == 3


def test_nothing_is_escalated_when_the_hourly_cap_is_already_used(monkeypatch):
    count, queued, _ = _capped(monkeypatch, [_row("sms")], fb_recent=3)
    assert count == 0 and queued == []


def test_newest_alerts_first_in_a_small_batch(monkeypatch):
    _, _, pool = _capped(monkeypatch, [], fb_recent=0)
    assert "ORDER BY o.id DESC" in pool.fetch_sql and "LIMIT $3" in pool.fetch_sql
    assert pool.fetch_args[2] == channel_health.MAX_PER_SWEEP == 10
