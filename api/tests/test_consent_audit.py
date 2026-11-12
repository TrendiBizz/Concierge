"""Consent must say WHO acted: owner click, operator grant, or out-of-band SQL."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from app import channel_authorization


class FakeConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((" ".join(query.split()), args))
        return "SELECT 1"

    async def fetchrow(self, query, *args):
        return {"authorized": True, "updated_at": None}

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        @asynccontextmanager
        async def _acquire():
            yield conn

        return _acquire()


def test_owner_grant_sets_the_actor_for_the_trigger(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(channel_authorization.db, "pool", lambda: FakePool(conn))
    body = channel_authorization.ChannelAuthorization(
        channel="email_read", authorized=True, acknowledgement=True)
    result = asyncio.run(channel_authorization.record_authorization(
        "tenant-1", "user-1", body, actor_kind="owner", actor_label="owner@example.com"))
    assert result["actor_kind"] == "owner"
    settings_calls = [c for c in conn.executed if "set_config" in c[0]]
    assert settings_calls[0][1] == ("owner", "owner@example.com")
    # The audit row is written by the database trigger, not by the application, so a
    # direct-SQL change cannot bypass it either.
    assert not any("INSERT INTO tenant_channel_authorization_audit" in c[0]
                   for c in conn.executed)


def test_operator_grant_is_labelled_as_an_operator(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(channel_authorization.db, "pool", lambda: FakePool(conn))
    body = channel_authorization.ChannelAuthorization(
        channel="email_read", authorized=True, acknowledgement=True)
    result = asyncio.run(channel_authorization.record_authorization(
        "tenant-1", None, body, actor_kind="operator",
        actor_label="operator@trendibizz.com: customer asked by phone"))
    assert result["actor_kind"] == "operator"
    assert conn.executed[0][1][0] == "operator"


def test_grant_without_acknowledgement_is_refused(monkeypatch):
    monkeypatch.setattr(channel_authorization.db, "pool",
                        lambda: (_ for _ in ()).throw(AssertionError("no database access")))
    body = channel_authorization.ChannelAuthorization(
        channel="email_read", authorized=True, acknowledgement=False)
    try:
        asyncio.run(channel_authorization.record_authorization("t", "u", body))
    except ValueError as exc:
        assert "acknowledgement" in str(exc)
    else:
        raise AssertionError("must refuse an unacknowledged grant")
