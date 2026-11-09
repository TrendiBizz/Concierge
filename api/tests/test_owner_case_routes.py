"""Owner-facing case view and human takeover.

The audit asks for human takeover and for one durable customer history. Before this, an owner could
not see a customer's cross-channel history in the portal, and could not stop the assistant replying
to someone they had started answering themselves -- takeover existed only behind the gateway-only
`hermes_ops` router, which answers 404 unless a gateway integration is configured.

These drive the real routes through FastAPI's TestClient. The subject is tenant isolation and the
effect of the pause, so the database is substituted at the pool boundary.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import casetimeline, main, owner_auth

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
LEAD = "33333333-3333-3333-3333-333333333333"
CASE = "44444444-4444-4444-4444-444444444444"


@pytest.fixture()
def client():
    """The real app with an authenticated owner.

    The override is keyed by the dependency object itself and must NOT be combined with a
    monkeypatch on the same attribute: replacing the attribute first makes the override key and the
    route's dependency reference diverge, and every request 401s.
    """
    async def auth():
        return {"tenant_id": TENANT_A, "id": "u1", "email": "o@a.example", "role": "owner"}

    main.app.dependency_overrides[owner_auth.current_user] = auth
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _pool(**over):
    """A pool whose fetchrow/fetchval answers per-query, so tenant scoping is observable."""
    calls = []
    base = {
        "fetchrow": AsyncMock(return_value=None),
        "fetchval": AsyncMock(return_value=None),
        "execute": AsyncMock(return_value="UPDATE 1"),
        "fetch": AsyncMock(return_value=[]),
        "acquire": None,
    }
    base.update(over)
    base["calls"] = calls
    return SimpleNamespace(**base)


def test_case_view_requires_the_lead_to_belong_to_the_tenant(client, monkeypatch):
    """A lead id from another business must resolve to nothing, not to their data."""
    monkeypatch.setattr(main.tenants, "get_by_id", AsyncMock(return_value={"id": TENANT_A, "sla_minutes": 60}))
    # The scoped query finds nothing, as it would for another tenant's lead.
    monkeypatch.setattr(main.db, "pool", lambda: _pool(fetchrow=AsyncMock(return_value=None)))

    resp = client.get(f"/owner/crm/leads/{LEAD}/case")
    assert resp.status_code == 404


def test_case_view_reports_channels_deadline_and_events(client, monkeypatch):
    monkeypatch.setattr(main.tenants, "get_by_id", AsyncMock(return_value={
        "id": TENANT_A, "timezone": "Pacific/Auckland", "sla_minutes": 60}))
    lead = {"id": LEAD, "case_id": CASE, "name": "Hana", "phone": "+6421555123",
            "email": "hana@example.com", "message": "quote", "status": "new",
            "created_at": "2026-11-10T00:00:00+00:00", "channel": "email"}
    case = {"case_key": "phone:+6421555123", "primary_phone": "+6421555123",
            "primary_email": "hana@example.com", "automation_paused": False, "takeover_at": None}
    rows = [
        {"channel": "email", "direction": "inbound", "body": "quote please",
         "occurred_at": None, "answered_at": None},
        {"channel": "sms", "direction": "inbound", "body": "any update?",
         "occurred_at": None, "answered_at": None},
    ]
    pool = _pool()
    pool.fetchrow = AsyncMock(side_effect=[lead, case])
    monkeypatch.setattr(main.db, "pool", lambda: pool)
    monkeypatch.setattr(casetimeline, "timeline", AsyncMock(return_value=rows))

    body = client.get(f"/owner/crm/leads/{LEAD}/case").json()
    assert body["case_key"] == "phone:+6421555123"
    assert body["channels_seen"] == ["email", "sms"]
    assert body["event_count"] == 2
    assert body["deadline"]["due_at"] == "2026-11-10T01:00:00+00:00"


def test_takeover_pauses_the_case(client, monkeypatch):
    lead = {"case_id": CASE}
    case = {"case_key": "phone:+6421555123"}
    pool = _pool()
    pool.fetchrow = AsyncMock(side_effect=[lead, case])
    monkeypatch.setattr(main.db, "pool", lambda: pool)
    paused = AsyncMock(return_value=True)
    monkeypatch.setattr(casetimeline, "set_takeover", paused)

    resp = client.post(f"/owner/crm/leads/{LEAD}/takeover", json={"paused": True})
    assert resp.status_code == 200
    assert resp.json()["automation_paused"] is True
    paused.assert_awaited()
    assert paused.await_args.kwargs["paused"] is True
    assert paused.await_args.kwargs["case_key"] == "phone:+6421555123"


def test_takeover_can_be_handed_back(client, monkeypatch):
    pool = _pool()
    pool.fetchrow = AsyncMock(side_effect=[{"case_id": CASE}, {"case_key": "phone:+6421555123"}])
    monkeypatch.setattr(main.db, "pool", lambda: pool)
    resumed = AsyncMock(return_value=True)
    monkeypatch.setattr(casetimeline, "set_takeover", resumed)

    resp = client.post(f"/owner/crm/leads/{LEAD}/takeover", json={"paused": False})
    assert resp.status_code == 200
    assert resumed.await_args.kwargs["paused"] is False


def test_takeover_on_a_lead_with_no_case_explains_itself(client, monkeypatch):
    """A lead with no history yet must give a clear reason, not a silent success."""
    pool = _pool()
    pool.fetchrow = AsyncMock(return_value={"case_id": None})
    monkeypatch.setattr(main.db, "pool", lambda: pool)

    resp = client.post(f"/owner/crm/leads/{LEAD}/takeover", json={"paused": True})
    assert resp.status_code == 409
    assert "conversation" in resp.json()["detail"].lower()


def test_takeover_is_scoped_to_the_callers_tenant(client, monkeypatch):
    """The lookup must carry the caller's tenant, so another business's lead cannot be paused."""
    seen = {}

    async def fetchrow(sql, *args):
        seen["sql"] = sql
        seen["args"] = args
        return None

    monkeypatch.setattr(main.db, "pool", lambda: _pool(fetchrow=fetchrow))
    resp = client.post(f"/owner/crm/leads/{LEAD}/takeover", json={"paused": True})
    assert resp.status_code == 404
    assert "tenant_id" in seen["sql"], "the query must be tenant-scoped"
    assert seen["args"][0] == TENANT_A
