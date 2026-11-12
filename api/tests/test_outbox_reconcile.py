"""An SMS whose phone never sends a receipt must not stay "in flight" forever."""
import asyncio

from app import outbox


class FakePool:
    def __init__(self, stalled):
        self.stalled = stalled
        self.executed = []
        self.fetch_args = None

    async def fetch(self, sql, *args):
        self.fetch_args = (sql, args)
        return self.stalled

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "UPDATE 1"


def test_stalled_sms_rows_are_failed_not_left_in_flight(monkeypatch):
    pool = FakePool([{"outbox_id": 264}, {"outbox_id": 267}])
    monkeypatch.setattr(outbox.db, "pool", lambda: pool)

    assert asyncio.run(outbox.reconcile_stale_device_sms()) == 2
    assert len(pool.executed) == 2
    for sql, args in pool.executed:
        assert "status='failed'" in sql
        assert args[1] == "Phone never confirmed send; reconcile before retry"
    # The sweep only looks at SMS rows that are waiting for a phone receipt.
    sql, args = pool.fetch_args
    assert "o.channel='sms'" in sql
    assert "awaiting_receipt" in sql
    assert args == (outbox.STALE_SMS_INTERVAL,)


def test_rows_without_an_outbox_link_are_skipped(monkeypatch):
    pool = FakePool([{"outbox_id": None}])
    monkeypatch.setattr(outbox.db, "pool", lambda: pool)

    assert asyncio.run(outbox.reconcile_stale_device_sms()) == 0
    assert pool.executed == []
