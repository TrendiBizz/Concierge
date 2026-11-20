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


