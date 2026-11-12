"""Item C — one timeline per customer.

The channel merge itself lives in casetimeline (already covered by test_case_timeline.py). This
covers the two new pure helpers and the three owner routes that expose it.
"""
import asyncio
import uuid

import httpx
from unittest.mock import AsyncMock

from app import casetimeline, db, owner_auth
from app.main import app


# ------------------------------------------------------------------ pure helpers

def test_summarise_counts_every_channel():
    events = [
        {"channel": "email", "direction": "inbound"},
        {"channel": "email", "direction": "outbound"},
        {"channel": "phone", "direction": "inbound"},
        {"channel": "chat", "direction": "inbound"},
    ]
    summary = casetimeline.summarise(events)
    assert summary["event_count"] == 4
    assert summary["by_channel"] == {"email": 2, "phone": 1, "chat": 1}
    assert summary["channels"] == ["chat", "email", "phone"]
    assert summary["labels"] == ["Website chat", "Email", "Phone"]


def test_summarise_handles_an_empty_history_and_unknown_channels():
    assert casetimeline.summarise([]) == {
        "event_count": 0, "by_channel": {}, "channels": [], "labels": []}
    odd = casetimeline.summarise([{"channel": "carrier-pigeon"}])
    assert odd["labels"] == ["Carrier-Pigeon"]


def test_contact_label_prefers_a_name_then_falls_back_to_an_identifier():
    assert casetimeline.contact_label({"display_name": "Ana"}) == "Ana"
    assert casetimeline.contact_label({"primary_phone": "+64210000000"}) == "+64210000000"
    assert casetimeline.contact_label({"primary_email": "a@b.test"}) == "a@b.test"
    assert casetimeline.contact_label({"case_key": "p:+64210000000"}) == "p:+64210000000"
    assert casetimeline.contact_label({}) == "Unknown contact"
    assert casetimeline.contact_label(None) == "Unknown contact"


# ------------------------------------------------------------------ owner routes

def _client(auth, monkeypatch, pool):
    async def run(path, method="GET", body=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="https://test") as c:
            return await c.request(method, path, json=body)

    monkeypatch.setattr(db, "pool", lambda: pool)
    app.dependency_overrides[owner_auth.current_user] = auth
    return run


def test_contacts_list_names_and_labels_each_customer(monkeypatch):
    tenant = uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner"}

    pool = type("P", (), {
        "fetch": AsyncMock(return_value=[{
            "case_key": "p:+64210000000", "display_name": "", "primary_phone": "+64210000000",
            "primary_email": "", "automation_paused": False, "takeover_at": None,
            "updated_at": None, "event_count": 3, "channels": "email,phone",
            "last_at": None,
        }]),
    })()
    run = _client(auth, monkeypatch, pool)
    try:
        result = asyncio.run(run("/owner/contacts?q=ana"))
        assert result.status_code == 200
        body = result.json()
        assert body["count"] == 1
        contact = body["contacts"][0]
        assert contact["label"] == "+64210000000"
        assert contact["channels"] == ["email", "phone"]
        # The search term is a bound parameter, never interpolated into the SQL.
        assert pool.fetch.await_args.args[1:] == (tenant, "ana", 50)
        # And the list can never cross tenants (item C is a customer-facing view, not an admin one).
        assert "c.tenant_id = $1" in " ".join(pool.fetch.await_args.args[0].split())
    finally:
        app.dependency_overrides.clear()


def test_contact_timeline_404s_for_a_stranger(monkeypatch):
    tenant = uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner"}

    pool = type("P", (), {"fetchrow": AsyncMock(return_value=None)})()
    run = _client(auth, monkeypatch, pool)
    try:
        assert asyncio.run(run("/owner/contacts/p:%2B6421/timeline")).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_contact_timeline_merges_channels_and_related_records(monkeypatch):
    tenant, case_id, lead_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner"}

    pool = type("P", (), {
        "fetchrow": AsyncMock(return_value={
            "id": case_id, "case_key": "p:+64210000000", "display_name": "Ana",
            "primary_phone": "+64210000000", "primary_email": "",
            "automation_paused": True, "takeover_at": None,
        }),
        "fetch": AsyncMock(side_effect=[
            [{"id": lead_id, "status": "new", "channel": "phone", "message": "Asked for a quote",
              "created_at": None}],
            [{"starts_at": None, "status": "booked", "name": "Ana"}],
        ]),
    })()
    monkeypatch.setattr(casetimeline, "timeline", AsyncMock(return_value=[
        {"channel": "email", "direction": "inbound", "body": "Hi", "occurred_at": None,
         "answered_at": None},
        {"channel": "phone", "direction": "inbound", "body": "Called", "occurred_at": None,
         "answered_at": None},
    ]))
    run = _client(auth, monkeypatch, pool)
    try:
        result = asyncio.run(run("/owner/contacts/p:%2B64210000000/timeline"))
        assert result.status_code == 200
        body = result.json()
        assert body["label"] == "Ana"
        assert body["event_count"] == 2
        assert body["channels"] == ["email", "phone"]
        assert [e["channel_label"] for e in body["events"]] == ["Email", "Phone"]
        assert body["enquiries"][0]["status"] == "new"
        assert body["appointments"][0]["status"] == "booked"
        assert body["automation_paused"] is True
    finally:
        app.dependency_overrides.clear()


def test_takeover_requires_a_reason_and_is_recorded(monkeypatch):
    tenant = uuid.uuid4()

    async def auth():
        return {"tenant_id": tenant, "role": "owner", "email": "owner@example.test"}

    pool = type("P", (), {})()
    run = _client(auth, monkeypatch, pool)
    calls = {}

    async def set_takeover(tenant_id, *, case_key, paused, by="owner"):
        calls.update(tenant_id=tenant_id, case_key=case_key, paused=paused, by=by)
        return True

    monkeypatch.setattr(casetimeline, "set_takeover", set_takeover)
    try:
        blank = asyncio.run(run("/owner/contacts/p:x/takeover", "PUT", {"paused": True}))
        assert blank.status_code == 422
        assert calls == {}

        ok = asyncio.run(run("/owner/contacts/p:x/takeover", "PUT",
                             {"paused": True, "reason": "rang them back"}))
        assert ok.status_code == 200
        assert calls["paused"] is True
        assert "rang them back" in calls["by"]
        assert calls["tenant_id"] == tenant

        # Resuming needs no reason and is never blocked.
        calls.clear()
        resume = asyncio.run(run("/owner/contacts/p:x/takeover", "PUT",
                                {"paused": False, "reason": ""}))
        assert resume.status_code == 200 and calls["paused"] is False
    finally:
        app.dependency_overrides.clear()


def test_takeover_404s_when_the_contact_does_not_exist(monkeypatch):
    async def auth():
        return {"tenant_id": uuid.uuid4(), "role": "owner"}

    async def set_takeover(*_a, **_k):
        return False

    monkeypatch.setattr(casetimeline, "set_takeover", set_takeover)
    run = _client(auth, monkeypatch, type("P", (), {})())
    try:
        result = asyncio.run(run("/owner/contacts/p:missing/takeover", "PUT",
                                 {"paused": False, "reason": ""}))
        assert result.status_code == 404
    finally:
        app.dependency_overrides.clear()
