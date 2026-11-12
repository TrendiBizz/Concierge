"""The supervision audit trail and the console actions behind it.

Two things are being pinned down: that a duration is derived only from real timestamps, and that
no code path can show a listener who is not there (or lose one who is) without recording why.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx

from app import asterisk_ami, call_control, db, live_calls, owner_auth, supervision
from app.main import app

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)


def row(**over):
    base = {"id": 7, "call_sid": "ast:abc", "mode": "listen", "supervisor": "owner@example.test",
            "supervisor_number": "+64211234567", "spy_channel": "PJSIP/concierge-reg-00000009",
            "started_at": NOW - timedelta(seconds=40), "ended_at": None, "ended_reason": ""}
    base.update(over)
    return base


# ------------------------------------------------------------------ pure rules

def test_an_open_leg_reports_time_so_far_not_a_completed_session():
    shown = supervision.summarise(row(), NOW)
    assert shown["open"] is True and shown["seconds"] == 40 and shown["ended_at"] is None


def test_a_closed_leg_reports_exactly_its_own_window():
    closed = row(ended_at=NOW - timedelta(seconds=15), ended_reason=supervision.HUNG_UP)
    shown = supervision.summarise(closed, NOW)
    assert shown["open"] is False and shown["seconds"] == 25
    assert shown["ended_reason"] == supervision.HUNG_UP


def test_a_duration_is_never_negative_even_if_the_clock_moved():
    assert supervision.duration_seconds(row(started_at=NOW + timedelta(minutes=2)), NOW) == 0
    assert supervision.duration_seconds(row(started_at=None), NOW) == 0
    assert supervision.duration_seconds(row(ended_at=NOW - timedelta(minutes=5)), NOW) == 0


def test_every_mode_has_a_label_and_an_unknown_one_is_still_shown():
    assert [supervision.label(m) for m in ("listen", "whisper", "join")] == \
        ["Listen in", "Whisper", "Join"]
    assert supervision.label("BRAWL") == "Brawl"


# ------------------------------------------------------------------ the record

class Pool:
    """Records statements, answers like the tables the module queries."""

    def __init__(self, fetch=(), fetchrow=None, fetchval=None):
        self.fetch = AsyncMock(return_value=list(fetch))
        self.fetchrow = AsyncMock(return_value=fetchrow)
        self.fetchval = AsyncMock(return_value=fetchval)
        self.execute = AsyncMock(return_value="UPDATE 1")
        self.calls = []

    async def _fetch(self, sql, *args):
        self.calls.append((" ".join(sql.split()), args))
        return list(self.fetch.return_value)


def _pool(monkeypatch, pool):
    monkeypatch.setattr(supervision.db, "pool", lambda: pool)
    return pool


def test_a_leg_is_recorded_before_it_is_dialled_and_carries_its_own_marker(monkeypatch):
    pool = _pool(monkeypatch, Pool(fetchrow={"id": 11, "started_at": NOW}))
    record = asyncio.run(supervision.start(
        "t1", "ast:abc", "whisper", supervisor="a@b.test", number="+64211234567", marker="deadbeef"))
    assert record["id"] == 11
    sql, args = pool.fetchrow.call_args.args[0], pool.fetchrow.call_args.args[1:]
    assert "INSERT INTO supervision_sessions" in " ".join(sql.split())
    assert args == ("t1", "ast:abc", "whisper", "a@b.test", "+64211234567", "deadbeef")


def test_stopping_only_closes_a_leg_that_is_still_open(monkeypatch):
    pool = _pool(monkeypatch, Pool(fetchrow=row(ended_at=NOW, ended_reason="stopped")))
    closed = asyncio.run(supervision.stop("t1", 7, "the supervisor stopped it"))
    assert closed["ended_reason"] == "stopped"
    sql = " ".join(pool.fetchrow.call_args.args[0].split())
    assert "ended_at IS NULL" in sql          # a second stop cannot rewrite the first
    assert "ended_at = now()" in sql


def test_a_call_ending_closes_its_legs_at_the_call_end_time(monkeypatch):
    pool = _pool(monkeypatch, Pool())
    pool.fetch = AsyncMock(side_effect=[[{"id": 1}, {"id": 2}], []])
    assert asyncio.run(supervision.close_ended_calls("t1")) == 2
    ended_sql = " ".join(pool.fetch.call_args_list[0].args[0].split())
    assert "COALESCE(pc.ended_at, now())" in ended_sql   # the call's end, not the moment we read
    assert "pc.status <> 'in_progress'" in ended_sql
    assert pool.fetch.call_count == 2                    # plus the removed-call sweep


def test_a_leg_the_pbx_no_longer_has_is_closed_but_a_live_one_is_left_alone(monkeypatch):
    pool = _pool(monkeypatch, Pool(
        fetch=[{"id": 1, "spy_channel": "PJSIP/gone-00000001", "marker": ""},
               {"id": 2, "spy_channel": "PJSIP/live-00000002", "marker": ""}]))
    pool.fetchrow = AsyncMock(return_value=row(id=1))
    closed = asyncio.run(supervision.close_missing_legs("t1", {"PJSIP/live-00000002"}))
    assert closed == 1
    assert [c.args[2] for c in pool.fetchrow.call_args_list] == [1]
    assert pool.fetchrow.call_args.args[3] == supervision.HUNG_UP

    assert asyncio.run(supervision.close_missing_legs(
        "t1", {"PJSIP/gone-00000001", "PJSIP/live-00000002"})) == 0


def test_a_leg_is_live_when_the_pbx_still_carries_its_marker_under_another_name(monkeypatch):
    # What the live probe found: the PBX identifies the leg by CONCIERGE_SPY, and a leg that was
    # stored under a stale or wrong channel name must not be declared hung up while it is live.
    pool = _pool(monkeypatch, Pool(fetch=[
        {"id": 3, "spy_channel": "PJSIP/stale-00000003", "marker": "aa11"},
        {"id": 4, "spy_channel": "PJSIP/other-00000004", "marker": "bb22"}]))
    pool.fetchrow = AsyncMock(return_value=row(id=4))
    closed = asyncio.run(supervision.close_missing_legs("t1", {"PJSIP/renamed-00000005": "aa11"}))
    assert closed == 1
    assert [c.args[2] for c in pool.fetchrow.call_args_list] == [4]


# ------------------------------------------------------------------ starting a listen

def _tenant():
    return {"id": "t1", "slug": "pukeko", "name": "Pukeko", "notify_phone": "+64211234567"}


class Settings:
    asterisk_channel_dial = "PJSIP/<number>@concierge-reg"


def _arm_supervise(monkeypatch, pool, attach=None):
    monkeypatch.setattr(live_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(live_calls, "get_settings", lambda: Settings)
    monkeypatch.setattr(live_calls, "owner_voice_number",
                        AsyncMock(return_value="+64211234567"))
    monkeypatch.setattr(live_calls, "engine", lambda call: "asterisk")
    monkeypatch.setattr(live_calls.supervision_audit, "start",
                        AsyncMock(return_value={"id": 11, "started_at": NOW}))
    monkeypatch.setattr(live_calls.supervision_audit, "stop", AsyncMock(return_value=row(id=11)))
    monkeypatch.setattr(live_calls.supervision_audit, "attach_channel",
                        AsyncMock(return_value=None))
    monkeypatch.setattr(live_calls.call_control, "attach_supervisor",
                        attach or AsyncMock(return_value="PJSIP/concierge-reg-00000009"))


def _call():
    return {"call_sid": "ast:abc", "status": "in_progress", "started_at": NOW,
            "from_number": "+649000", "session_id": "s1"}


def test_a_listen_is_recorded_before_the_ring_and_returns_its_audit_id(monkeypatch):
    _arm_supervise(monkeypatch, Pool())
    order = []
    monkeypatch.setattr(live_calls.call_control, "attach_supervisor",
                        AsyncMock(side_effect=lambda *a, **k: order.append(k.get("spy_marker"))
                                  or "PJSIP/concierge-reg-00000009"))
    result = asyncio.run(live_calls.supervise(_tenant(), _call(), "listen",
                                             supervisor="owner@example.test"))
    assert result["supervision_id"] == 11 and result["mode"] == "listen"
    marker = live_calls.call_control.attach_supervisor.call_args.kwargs["spy_marker"]
    assert marker and len(marker) == 16
    live_calls.supervision_audit.start.assert_awaited_once()
    live_calls.supervision_audit.attach_channel.assert_awaited_once_with(
        11, "PJSIP/concierge-reg-00000009")


def test_a_failed_ring_closes_the_record_and_says_why(monkeypatch):
    async def boom(*_a, **_k):
        raise asterisk_ami.AmiError("no route to the supervisor")

    _arm_supervise(monkeypatch, Pool(), attach=boom)
    try:
        asyncio.run(live_calls.supervise(_tenant(), _call(), "listen"))
        raise AssertionError("the ring failure must reach the console")
    except asterisk_ami.AmiError:
        pass
    reason = live_calls.supervision_audit.stop.call_args.args[2]
    assert reason.startswith(supervision.RING_FAILED)


def test_no_listener_is_recorded_when_the_owner_cannot_be_rung(monkeypatch):
    _arm_supervise(monkeypatch, Pool())
    monkeypatch.setattr(live_calls, "owner_voice_number", AsyncMock(return_value=""))
    try:
        asyncio.run(live_calls.supervise(_tenant(), _call(), "listen"))
        raise AssertionError("no number must refuse, not pretend")
    except call_control.CallControlUnavailable:
        pass
    live_calls.supervision_audit.start.assert_not_awaited()


def test_stopping_hangs_up_the_leg_and_closes_the_record(monkeypatch):
    _arm_supervise(monkeypatch, Pool())
    monkeypatch.setattr(live_calls.supervision_audit, "open_for_call",
                        AsyncMock(return_value=[row()]))
    hangup = AsyncMock(return_value="Success")
    monkeypatch.setattr(live_calls.call_control, "hangup_leg", hangup)
    result = asyncio.run(live_calls.stop_supervision(_tenant(), "ast:abc",
                                                     by="owner@example.test"))
    assert result["stopped"] == 1
    hangup.assert_awaited_once_with("PJSIP/concierge-reg-00000009")
    assert "owner@example.test" in live_calls.supervision_audit.stop.call_args.args[2]


def test_stopping_ends_every_channel_carrying_the_marker_and_never_the_callers(
        monkeypatch):
    # What the live probe found: the stored channel used to be the *caller's*. Stop must act on
    # the leg's marker, and must end every channel that carries it (a Local leg is a pair).
    _arm_supervise(monkeypatch, Pool())
    monkeypatch.setattr(live_calls.supervision_audit, "open_for_call", AsyncMock(return_value=[
        row(marker="aa11", spy_channel="PJSIP/stale-00000009")]))
    monkeypatch.setattr(live_calls.call_control, "spy_legs", AsyncMock(return_value={
        "PJSIP/spy-00000009": "aa11",
        "Local/spy-00000009;2": "aa11",
        "PJSIP/caller-00000001": "",
    }))
    hangup = AsyncMock(return_value="Success")
    monkeypatch.setattr(live_calls.call_control, "hangup_leg", hangup)
    result = asyncio.run(live_calls.stop_supervision(_tenant(), "ast:abc"))
    assert result["stopped"] == 1
    ended = [call.args[0] for call in hangup.await_args_list]
    assert ended == ["PJSIP/spy-00000009", "Local/spy-00000009;2"]
    assert all("caller" not in channel for channel in ended)


def test_stopping_when_nobody_is_listening_says_so_without_inventing_a_leg(monkeypatch):
    _arm_supervise(monkeypatch, Pool())
    monkeypatch.setattr(live_calls.supervision_audit, "open_for_call", AsyncMock(return_value=[]))
    result = asyncio.run(live_calls.stop_supervision(_tenant(), "ast:abc"))
    assert result["stopped"] == 0 and "Nobody is listening" in result["note"]


# ------------------------------------------------------------------ routes

def _client(monkeypatch, tenant=None):
    tenant = tenant or uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner", "slug": "pukeko",
                "email": "owner@example.test"}

    app.dependency_overrides[owner_auth.current_user] = auth

    async def run(path, method="GET", body=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://test") as client:
            return await client.request(method, path, json=body)

    return run


def test_the_audit_view_is_tenant_scoped_newest_first_with_working_durations(monkeypatch):
    tenant = uuid.uuid4()
    seen = {}

    async def recent(tenant_id, limit):
        seen["tenant_id"], seen["limit"] = tenant_id, limit
        return [supervision.summarise(row(ended_at=NOW - timedelta(seconds=10)))]

    monkeypatch.setattr(supervision, "recent", recent)
    monkeypatch.setattr(live_calls, "reconcile_supervision", AsyncMock(return_value=0))
    run = _client(monkeypatch, tenant)
    try:
        response = asyncio.run(run("/owner/supervision?limit=5"))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["sessions"][0]["seconds"] == 30 and body["sessions"][0]["open"] is False
    assert seen == {"tenant_id": tenant, "limit": 5}


def test_stopping_supervision_404s_for_a_call_that_is_not_this_tenants(monkeypatch):
    import app.main as main_module

    async def require_tenant(_slug):
        return {"id": uuid.uuid4(), "slug": "pukeko", "name": "Pukeko"}

    monkeypatch.setattr(main_module, "_require_tenant", require_tenant)
    monkeypatch.setattr(db, "pool", lambda: Pool(fetchrow=None))
    run = _client(monkeypatch)
    try:
        response = asyncio.run(run("/owner/live-calls/sip:nope/supervise/stop", "POST", {}))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
