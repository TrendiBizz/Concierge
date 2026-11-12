"""Item B — live call supervision.

The rules are pure; the takeover is an ordering guarantee (pause → alert → end), so that is what
these tests pin down.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from unittest.mock import AsyncMock

from app import db, live_calls, owner_auth
from app.main import app

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)


def call(**over):
    base = {"call_sid": "sip:abc", "tenant_id": "t1", "session_id": "sip:abc",
            "from_number": "+64211234567", "to_number": "+6490000000",
            "status": "in_progress", "started_at": NOW - timedelta(seconds=95)}
    base.update(over)
    return base


# ------------------------------------------------------------------ rules

def test_only_calls_in_progress_and_recent_enough_are_live():
    assert live_calls.is_live(call(), NOW) is True
    assert live_calls.is_live(call(status="completed"), NOW) is False
    stale = call(started_at=NOW - timedelta(hours=5))
    assert live_calls.is_live(stale, NOW) is False
    assert live_calls.is_live(call(started_at=None), NOW) is True


def test_a_caller_without_a_number_is_still_identifiable():
    assert live_calls.caller_label(call()) == "+64211234567"
    assert live_calls.caller_label(call(from_number="  ")) == "Unknown caller"


def test_seconds_in_call_never_goes_negative():
    assert live_calls.seconds_in_call(call(), NOW) == 95
    assert live_calls.seconds_in_call(call(started_at=None), NOW) == 0
    assert live_calls.seconds_in_call(call(started_at=NOW + timedelta(minutes=1)), NOW) == 0


def test_the_transcript_tail_is_labelled_and_bounded():
    turns = [{"role": "user", "content": "f" * 3000},
             {"role": "assistant", "content": "Hello"}]
    tail = live_calls.transcript_tail(turns)
    assert [row["who"] for row in tail] == ["Caller", "Concierge"]
    assert len(tail[0]["text"]) == 2000

    many = [{"role": "user", "content": str(i)} for i in range(40)]
    assert len(live_calls.transcript_tail(many)) == live_calls.TAIL
    assert live_calls.transcript_tail(many)[-1]["text"] == "39"


def test_the_summary_flags_a_caller_who_has_not_spoken():
    silent = live_calls.summarise(call(), [], NOW)
    assert silent["caller_has_spoken"] is False
    spoke = live_calls.summarise(call(), [{"role": "user", "content": "hi"}], NOW)
    assert spoke["caller_has_spoken"] is True
    # Ring-back is only offered where we can actually end the AI call.
    assert silent["ring_back_available"] is True
    assert live_calls.summarise(call(call_sid="twilio-call"), [], NOW)["ring_back_available"] is False


# ------------------------------------------------------------------ takeover ordering

class OrderPool:
    def __init__(self, lead_id="lead-1", existing_task=False):
        self.lead_id = lead_id
        self.existing_task = existing_task
        self.executed = []
        self.order = []

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        text = " ".join(sql.split())
        if "SELECT id FROM leads" in text:
            return self.lead_id
        if "FROM tasks" in text:
            return "1" if self.existing_task else None
        return None

    async def fetchrow(self, sql, *args):
        return None

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        self.order.append("task" if "INSERT INTO tasks" in sql else "other")
        return "INSERT 0 1"


def _tenant():
    return {"id": "t1", "name": "Pukeko", "slug": "pukeko", "default_country_code": "64",
            "notify_email": "owner@example.test", "notify_phone": "", "sms_enabled": False}


def test_takeover_pauses_first_then_alerts_then_ends(monkeypatch):
    pool = OrderPool()
    order = []

    async def reconcile(tenant_id, **kw):
        order.append("reconcile")
        return {"id": "case-1", "case_key": "p:+64211234567"}

    async def set_takeover(tenant_id, *, case_key, paused, by):
        order.append(f"pause:{by}")
        return True

    async def queue(tenant, subject, body, dedupe, **kw):
        order.append("alert")
        assert "+64211234567" in body

    async def call_control(call_id, action):
        order.append(f"control:{action}")
        assert call_id == "abc"
        return True

    import app.phone_sip as phone_sip

    monkeypatch.setattr(live_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(live_calls.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(live_calls.casetimeline, "set_takeover", set_takeover)
    monkeypatch.setattr(live_calls.owner_notifications, "queue", queue)
    monkeypatch.setattr(phone_sip, "call_control", call_control)

    result = asyncio.run(live_calls.take_over(_tenant(), call(), by="owner@example.test"))

    assert result["paused"] is True and result["ended"] is True
    assert order == ["reconcile", "pause:owner@example.test: live call takeover", "alert",
                     "control:hangup"]
    tasks = [row for row in pool.executed if "INSERT INTO tasks" in row[0]]
    assert len(tasks) == 1 and "Ring back" in tasks[0][1][2]


def test_a_second_takeover_does_not_duplicate_the_callback_task(monkeypatch):
    pool = OrderPool(existing_task=True)

    async def reconcile(*_a, **_k):
        return {"id": "case-1", "case_key": "p:+64211234567"}

    async def set_takeover(*_a, **_k):
        return True

    async def queue(*_a, **_k):
        return None

    import app.phone_sip as phone_sip

    monkeypatch.setattr(live_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(live_calls.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(live_calls.casetimeline, "set_takeover", set_takeover)
    monkeypatch.setattr(live_calls.owner_notifications, "queue", queue)
    monkeypatch.setattr(phone_sip, "call_control", AsyncMock(return_value=True))

    asyncio.run(live_calls.take_over(_tenant(), call()))
    assert [row for row in pool.executed if "INSERT INTO tasks" in row[0]] == []


def test_a_hangup_failure_is_reported_not_raised(monkeypatch):
    pool = OrderPool()

    async def reconcile(*_a, **_k):
        return None

    async def queue(*_a, **_k):
        return None

    import app.phone_sip as phone_sip

    async def boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(live_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(live_calls.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(live_calls.owner_notifications, "queue", queue)
    monkeypatch.setattr(phone_sip, "call_control", boom)

    result = asyncio.run(live_calls.take_over(_tenant(), call()))
    assert result["ended"] is False
    assert result["note"]


def test_a_call_outside_the_sip_path_is_not_hung_up(monkeypatch):
    pool = OrderPool()
    control = AsyncMock(return_value=True)

    async def reconcile(*_a, **_k):
        return None

    async def queue(*_a, **_k):
        return None

    import app.phone_sip as phone_sip

    monkeypatch.setattr(live_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(live_calls.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(live_calls.owner_notifications, "queue", queue)
    monkeypatch.setattr(phone_sip, "call_control", control)

    result = asyncio.run(live_calls.take_over(_tenant(), call(call_sid="twilio:xyz")))
    assert result["ended"] is False
    assert "phone system" in result["note"]
    control.assert_not_awaited()


# ------------------------------------------------------------------ routes

def _client(auth, monkeypatch, pool):
    async def run(path, method="GET", body=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://test") as c:
            return await c.request(method, path, json=body)

    monkeypatch.setattr(db, "pool", lambda: pool)
    app.dependency_overrides[owner_auth.current_user] = auth
    return run


def test_takeover_409s_for_a_call_that_already_ended(monkeypatch):
    tenant = uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner", "slug": "pukeko"}

    ended = dict(call(status="completed"))
    ended["tenant_id"] = tenant
    pool = type("P", (), {
        "fetchrow": AsyncMock(return_value=ended),
        "fetch": AsyncMock(return_value=[]),
    })()
    import app.main as main_module

    async def require_tenant(_slug):
        return {"id": tenant, "slug": "pukeko", "name": "Pukeko"}

    monkeypatch.setattr(main_module, "_require_tenant", require_tenant)
    run = _client(auth, monkeypatch, pool)
    try:
        result = asyncio.run(run("/owner/live-calls/sip:abc/takeover", "POST", {}))
        assert result.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_takeover_404s_for_another_tenants_call(monkeypatch):
    async def auth():
        return {"tenant_id": uuid.uuid4(), "role": "owner", "slug": "pukeko"}

    import app.main as main_module

    async def require_tenant(_slug):
        return {"id": uuid.uuid4(), "slug": "pukeko", "name": "Pukeko"}

    monkeypatch.setattr(main_module, "_require_tenant", require_tenant)
    pool = type("P", (), {"fetchrow": AsyncMock(return_value=None)})()
    run = _client(auth, monkeypatch, pool)
    try:
        result = asyncio.run(run("/owner/live-calls/sip:nope/takeover", "POST", {}))
        assert result.status_code == 404
    finally:
        app.dependency_overrides.clear()
