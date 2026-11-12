"""A phone line must not go live for a business whose owner cannot be told about enquiries."""
import asyncio

import pytest
from fastapi import HTTPException

from app import channel_health, main


class FakePool:
    def __init__(self, channels=()):
        self.channels = channels
        self.sql = ""

    async def fetch(self, sql, *args):
        self.sql = " ".join(sql.split())
        return [{"channel": c} for c in self.channels]


def _tenant(**over):
    base = {"id": "t1", "slug": "pukeko-construction", "name": "Pukeko Construction",
            "notify_phone": "+6421824305", "notify_email": "conrad@pukekoconstruction.co.nz",
            "phone_enabled": False}
    base.update(over)
    return base


def _blockers(monkeypatch, tenant, channels=()):
    pool = FakePool(channels)
    monkeypatch.setattr(channel_health.db, "pool", lambda: pool)
    return asyncio.run(channel_health.go_live_blockers(tenant)), pool


def test_ready_when_contacts_set_and_an_alert_was_delivered(monkeypatch):
    problems, pool = _blockers(monkeypatch, _tenant(), channels=("email",))
    assert problems == []
    # Only DELIVERED alerts count as proof, never merely queued or failed ones.
    assert "status = 'sent'" in pool.sql and "kind = 'owner_alert'" in pool.sql


def test_blocked_without_any_delivered_alert(monkeypatch):
    problems, _ = _blockers(monkeypatch, _tenant())
    assert len(problems) == 1 and "test alert" in problems[0].lower()


def test_blocked_without_owner_contact_details(monkeypatch):
    problems, _ = _blockers(monkeypatch, _tenant(notify_phone="", notify_email="  "), channels=("sms",))
    assert any("mobile" in p for p in problems)
    assert any("email" in p for p in problems)


def _patch_admin(monkeypatch, current, blockers):
    updates = []

    async def require_tenant(slug):
        return current

    async def update(slug, changes):
        updates.append(changes)
        return {**current, **changes}

    async def go_live_blockers(tenant):
        return blockers

    monkeypatch.setattr(main, "_require_tenant", require_tenant)
    monkeypatch.setattr(main.tenants, "update", update)
    monkeypatch.setattr(main.channel_health, "go_live_blockers", go_live_blockers)
    monkeypatch.setattr(main, "_with_snippet", lambda t: t)
    return updates


def _patch(slug, **fields):
    return asyncio.run(main.admin_update_tenant(slug, main.TenantUpdate(**fields["body"]), force=fields.get("force", False)))


def test_enabling_the_phone_is_refused_with_the_reasons(monkeypatch):
    updates = _patch_admin(monkeypatch, _tenant(), ["Send a test alert."])
    with pytest.raises(HTTPException) as err:
        _patch("pukeko-construction", body={"phone_enabled": True})
    assert err.value.status_code == 409
    assert err.value.detail["error"] == "alerts_not_proven"
    assert err.value.detail["blockers"] == ["Send a test alert."]
    assert updates == []  # nothing was changed


def test_operator_can_force_it_on(monkeypatch):
    updates = _patch_admin(monkeypatch, _tenant(), ["Send a test alert."])
    _patch("pukeko-construction", body={"phone_enabled": True}, force=True)
    assert updates == [{"phone_enabled": True}]


def test_enabling_goes_through_when_nothing_blocks(monkeypatch):
    updates = _patch_admin(monkeypatch, _tenant(), [])
    _patch("pukeko-construction", body={"phone_enabled": True})
    assert updates == [{"phone_enabled": True}]


def test_gate_ignores_disabling_already_enabled_and_unrelated_edits(monkeypatch):
    updates = _patch_admin(monkeypatch, _tenant(phone_enabled=True), ["blocked"])
    _patch("pukeko-construction", body={"phone_enabled": False})
    _patch("pukeko-construction", body={"phone_enabled": True})  # already on: not a go-live
    _patch("pukeko-construction", body={"greeting": "Kia ora"})
    assert len(updates) == 3


def test_operator_can_set_the_owner_mobile_through_the_api(monkeypatch):
    updates = _patch_admin(monkeypatch, _tenant(notify_phone=""), [])
    _patch("pukeko-construction", body={"notify_phone": "+6421824305"})
    assert updates == [{"notify_phone": "+6421824305"}]


def test_test_alert_goes_to_each_configured_channel(monkeypatch):
    queued = []

    async def enqueue(tenant_id, kind, channel, to_addr, body, subject="", dedupe_key=None, **kw):
        queued.append((channel, to_addr, kind, dedupe_key, subject))
        return True

    monkeypatch.setattr(channel_health.outbox, "enqueue", enqueue)
    result = asyncio.run(channel_health.send_test_alert(_tenant()))
    assert result == {"queued": ["email", "sms"]}
    assert {q[0] for q in queued} == {"email", "sms"}
    assert all(q[2] == "owner_alert" and q[3].startswith("test:t1:") for q in queued)

    queued.clear()
    only_email = asyncio.run(channel_health.send_test_alert(_tenant(notify_phone="")))
    assert only_email == {"queued": ["email"]}
