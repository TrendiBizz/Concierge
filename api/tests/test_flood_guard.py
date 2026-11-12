"""Flood protection where messages leave the platform (the 2026-11-13 mail loop)."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app import events, flood_guard, mailer, outbox, sms


class Pool:
    def __init__(self, counts=None, value=None):
        self.counts = counts or {}
        self.value = value
        self.fetchval_calls = 0
        self.executed = []
        self.args = ()

    async def fetchrow(self, sql, *args):
        self.args = args
        base = {"rcpt_10m": 0, "rcpt_1h": 0, "same_10m": 0, "tenant_1h": 0, "tenant_1d": 0,
                "global_1h": 0, "global_1d": 0}
        base.update(self.counts)
        return base

    async def fetchval(self, sql, *args):
        self.fetchval_calls += 1
        return self.value

    async def execute(self, sql, *args):
        self.executed.append(args)


def _row(channel="email", **over):
    base = {"id": 9, "tenant_id": "t1", "channel": channel, "to_addr": "Owner@Example.com",
            "subject": "Email enquiry", "body": "body", "kind": "owner_alert"}
    base.update(over)
    return base


def _check(monkeypatch, counts, channel="email"):
    pool = Pool(counts)
    monkeypatch.setattr(flood_guard.db, "pool", lambda: pool)
    return asyncio.run(flood_guard.check(_row(channel))), pool


def test_quiet_traffic_is_allowed(monkeypatch):
    reason, pool = _check(monkeypatch, {"rcpt_10m": 3, "tenant_1h": 20, "global_1d": 100})
    assert reason is None
    assert pool.args[1] == "owner@example.com"  # recipient is lower-cased


@pytest.mark.parametrize("counts,channel,reason", [
    ({"same_10m": 6}, "email", "identical_10min"),
    ({"same_10m": 3}, "sms", "identical_10min"),
    ({"rcpt_10m": 8}, "email", "recipient_10min"),
    ({"rcpt_1h": 25}, "email", "recipient_hour"),
    ({"tenant_1h": 100}, "email", "tenant_hour"),
    ({"tenant_1h": 40}, "sms", "tenant_hour"),
    ({"tenant_1d": 120}, "email", "tenant_day"),
    ({"global_1h": 150}, "email", "global_hour"),
    ({"global_1d": 270}, "email", "global_day"),
])
def test_each_limit_blocks_with_its_reason(monkeypatch, counts, channel, reason):
    assert _check(monkeypatch, counts, channel)[0] == reason


def test_just_under_every_limit_still_goes(monkeypatch):
    counts = {"same_10m": 5, "rcpt_10m": 7, "rcpt_1h": 24, "tenant_1h": 99, "tenant_1d": 119,
              "global_1h": 149, "global_1d": 269}
    assert _check(monkeypatch, counts)[0] is None


def test_other_channels_are_never_checked(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(flood_guard.db, "pool", lambda: pool)
    assert asyncio.run(flood_guard.check(_row("push"))) is None
    assert pool.args == ()


def test_robots_are_recognised():
    assert flood_guard.automated_message("noreply@shop.com")
    assert flood_guard.automated_message("Mail Delivery <MAILER-DAEMON@x.org>")
    assert flood_guard.automated_message("someone@example.com", "Automatic reply: holiday")
    assert flood_guard.automated_message("someone@example.com", "Out of Office until Monday")
    assert not flood_guard.automated_message("conrad@pukekoconstruction.co.nz", "Quote for a deck")
    assert not flood_guard.automated_message("", "")


def test_memory_window_allows_then_blocks_then_recovers(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(flood_guard.time, "monotonic", lambda: clock["t"])
    flood_guard._windows.clear()
    assert all(flood_guard.memory_allow("k", "a", 3, 60) for _ in range(3))
    assert flood_guard.memory_allow("k", "a", 3, 60) is False
    assert flood_guard.memory_allow("k", "b", 3, 60) is True  # keys are independent
    clock["t"] += 61
    assert flood_guard.memory_allow("k", "a", 3, 60) is True  # the window slid


def test_kill_switch_reads_the_flag_and_caches_it(monkeypatch):
    pool = Pool(value="1")
    monkeypatch.setattr(flood_guard.db, "pool", lambda: pool)
    flood_guard._flag.update(at=0.0, paused=False)
    assert asyncio.run(flood_guard.paused()) is True
    assert asyncio.run(flood_guard.paused()) is True
    assert pool.fetchval_calls == 1  # second call came from the 5 second cache
    flood_guard._flag.update(at=0.0, paused=False)


def test_pausing_writes_the_flag_and_takes_effect_at_once(monkeypatch):
    pool = Pool()
    monkeypatch.setattr(flood_guard.db, "pool", lambda: pool)
    asyncio.run(flood_guard.set_paused(True, "tester"))
    assert pool.executed[0] == ("1", "tester")
    assert asyncio.run(flood_guard.paused()) is True  # no DB read needed: cache updated
    asyncio.run(flood_guard.set_paused(False, "tester"))
    assert asyncio.run(flood_guard.paused()) is False
    flood_guard._flag.update(at=0.0, paused=False)


def test_paused_outbox_sends_nothing_and_touches_no_rows(monkeypatch):
    monkeypatch.setattr(outbox.flood_guard, "paused", AsyncMock(return_value=True))

    def boom():
        raise AssertionError("the queue must not be touched while paused")

    monkeypatch.setattr(outbox.db, "pool", boom)
    assert asyncio.run(outbox.process_once()) == 0


def test_a_blocked_message_is_skipped_with_the_reason_and_never_sent(monkeypatch):
    finished = []

    async def finish(row_id, status, error=""):
        finished.append((row_id, status, error))

    monkeypatch.setattr(outbox, "_finish", finish)
    monkeypatch.setattr(outbox.tenants, "get_by_id", AsyncMock(return_value={"id": "t1", "name": "Acme"}))
    monkeypatch.setattr(outbox.suppressions, "is_suppressed", AsyncMock(return_value=False))
    monkeypatch.setattr(outbox.flood_guard, "check", AsyncMock(return_value="recipient_10min"))
    send = AsyncMock()
    monkeypatch.setattr(outbox.mailer, "send_email", send)
    row = {"id": 5, "tenant_id": "t1", "kind": "owner_alert", "channel": "email", "to_addr": "o@example.com",
           "subject": "S", "body": "b", "campaign_id": None, "attempts": 1, "lead_id": None}
    asyncio.run(outbox._deliver(row))
    assert finished == [(5, "skipped", "flood_guard:recipient_10min")]
    send.assert_not_awaited()


def test_the_senders_refuse_when_their_last_resort_window_is_full(monkeypatch):
    monkeypatch.setattr(mailer.flood_guard, "memory_allow", lambda *a, **k: False)
    monkeypatch.setattr(mailer, "get_settings", lambda: type("S", (), {"email_configured": True})())
    with pytest.raises(mailer.EmailRateLimited):
        asyncio.run(mailer.send_email("a@example.com", "s", "b"))
    monkeypatch.setattr(sms.flood_guard, "memory_allow", lambda *a, **k: False)
    with pytest.raises(sms.SmsRateLimited):
        asyncio.run(sms.send_sms("+6421000000", "hi"))


def test_webhooks_are_capped_per_business(monkeypatch):
    monkeypatch.setattr(flood_guard, "memory_allow", lambda *a, **k: False)

    class NoNetwork:
        def __init__(self, *a, **k):
            raise AssertionError("must not call out once the cap is reached")

    monkeypatch.setattr(events.httpx, "AsyncClient", NoNetwork)
    tenant = {"slug": "acme", "name": "Acme", "lead_webhook_url": "https://example.com/hook"}
    asyncio.run(events._post(tenant, "lead.created", {}))


def test_a_broken_guard_fails_open_so_real_alerts_still_go(monkeypatch):
    class Broken:
        async def fetchrow(self, *a):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(flood_guard.db, "pool", lambda: Broken())
    assert asyncio.run(flood_guard.check(_row("email"))) is None
