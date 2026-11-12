"""Suppression: a dead or blocked address must never be mailed again."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import suppressions


class FakePool:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    async def execute(self, query, *args):
        self.calls.append(("execute", " ".join(query.split()), args))
        for marker, value in self.results.items():
            if marker in query:
                return value
        return "INSERT 0 1"

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", " ".join(query.split()), args))
        return self.results.get("fetchval")

    async def fetch(self, query, *args):
        self.calls.append(("fetch", " ".join(query.split()), args))
        return []


def _patch(monkeypatch, pool, audit=None):
    monkeypatch.setattr(suppressions.db, "pool", lambda: pool)
    sink = audit if audit is not None else AsyncMock()
    monkeypatch.setattr(suppressions.inbound_policy, "audit", sink)
    return sink


def test_hard_bounce_event_suppresses_and_closes_the_outbox_row(monkeypatch):
    pool = FakePool()
    audit = _patch(monkeypatch, pool)
    result = asyncio.run(suppressions.record_event({
        "event": "hard_bounce", "email": "Dead@Example.com",
        "message-id": "<outbox-1@x>", "reason": "550 user unknown",
        "tenant_id": "tenant-1",
    }))
    assert result == {"suppressed": True, "closed": 1}
    sql = [call[1] for call in pool.calls]
    assert any("INSERT INTO email_suppressions" in q for q in sql)
    assert any("UPDATE outbox SET status='failed'" in q for q in sql)
    insert_args = next(call[2] for call in pool.calls
                       if "INSERT INTO email_suppressions" in call[1])
    assert insert_args[1] == "dead@example.com"
    audit.assert_awaited()


def test_soft_bounce_does_not_suppress(monkeypatch):
    pool = FakePool()
    _patch(monkeypatch, pool)
    result = asyncio.run(suppressions.record_event({
        "event": "soft_bounce", "email": "alive@example.com", "tenant_id": "t1",
    }))
    assert result == {"deferred": True}
    assert not any("INSERT INTO email_suppressions" in call[1] for call in pool.calls)


def test_unknown_event_is_ignored(monkeypatch):
    pool = FakePool()
    _patch(monkeypatch, pool)
    assert asyncio.run(suppressions.record_event({
        "event": "opened", "email": "a@example.com", "tenant_id": "t1",
    })) == {"ignored": "opened"}
    assert pool.calls == []


def test_event_without_a_tenant_is_ignored(monkeypatch):
    pool = FakePool()
    _patch(monkeypatch, pool)
    assert asyncio.run(suppressions.record_event({"event": "spam", "email": "a@example.com"})) \
        == {"ignored": "missing address or tenant"}


def test_invalid_address_is_never_stored(monkeypatch):
    pool = FakePool()
    _patch(monkeypatch, pool)
    assert asyncio.run(suppressions.record_event({
        "event": "hard_bounce", "email": "not an address", "tenant_id": "t1",
    })) == {"ignored": "invalid address"}
    assert pool.calls == []


def test_is_suppressed_matches_the_normalised_address(monkeypatch):
    pool = FakePool({"fetchval": 1})
    _patch(monkeypatch, pool)
    assert asyncio.run(suppressions.is_suppressed("t1", " Dead@Example.com ")) is True
    args = pool.calls[0][2]
    assert args == ("t1", "dead@example.com")
