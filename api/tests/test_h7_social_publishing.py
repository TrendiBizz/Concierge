"""Tests for H7 live social publishing status, OAuth start routes, and approval flow."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app import main, social, social_bridge
from app.config import get_settings


def _owner_override(role: str = "owner"):
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "slug": "test-biz",
        "name": "Test Biz",
        "email": "owner@example.test",
        "role": role,
    }


def test_social_status_reflects_live_publishing_flag(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "social_service_enabled", True, raising=False)
    monkeypatch.setattr(s, "social_live_publishing", True, raising=False)
    monkeypatch.setattr(
        social_bridge,
        "provider_status",
        AsyncMock(return_value={
            "linkedin": True,
            "linkedin_organization": True,
            "facebook": True,
            "instagram": True,
            "google_business": True,
            "tiktok": True,
            "x": True,
        }),
    )
    main.app.dependency_overrides[main.owner_auth.current_user] = lambda: _owner_override("owner")
    try:
        client = TestClient(main.app)
        resp = client.get("/owner/social/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["live_publishing"] is True
        for net in ("facebook", "instagram", "linkedin", "linkedin_organization", "x", "tiktok", "google_business"):
            assert body["providers"][net] is True

        monkeypatch.setattr(s, "social_live_publishing", False, raising=False)
        resp2 = client.get("/owner/social/status")
        assert resp2.status_code == 200
        assert resp2.json()["live_publishing"] is False
    finally:
        main.app.dependency_overrides.clear()


def test_social_oauth_start_routes_all_seven_networks(monkeypatch):
    monkeypatch.setattr(get_settings(), "social_service_enabled", True, raising=False)
    monkeypatch.setattr(social.store, "ensure_customer", AsyncMock(return_value="test-biz"))
    monkeypatch.setattr(
        social.oauth,
        "start_oauth",
        AsyncMock(side_effect=lambda slug, net: {"authorization_url": f"https://provider.example/auth?net={net}", "state": "s" * 40}),
    )
    main.app.dependency_overrides[main.owner_auth.current_user] = lambda: _owner_override("owner")
    try:
        client = TestClient(main.app)
        routes = [
            "/owner/social/oauth/meta/facebook/start",
            "/owner/social/oauth/meta/instagram/start",
            "/owner/social/oauth/linkedin/start",
            "/owner/social/oauth/linkedin_organization/start",
            "/owner/social/oauth/x/start",
            "/owner/social/oauth/tiktok/start",
            "/owner/social/oauth/google/start",
        ]
        for route in routes:
            r = client.post(route)
            assert r.status_code == 200, f"{route} failed: {r.text}"
            data = r.json()
            assert data["authorization_url"].startswith("https://")
            assert len(data["state"]) >= 32
    finally:
        main.app.dependency_overrides.clear()


def test_social_draft_submit_approval_and_reject_flow(monkeypatch):
    monkeypatch.setattr(get_settings(), "social_service_enabled", True, raising=False)
    monkeypatch.setattr(social.store, "ensure_customer", AsyncMock(return_value="test-biz"))
    monkeypatch.setattr(
        social.store,
        "list_accounts",
        AsyncMock(return_value=[{"id": "acct_1234567890123456", "network": "facebook", "display_name": "Trendi", "needs_reauth": False}]),
    )
    monkeypatch.setattr(social.store, "get_rules", AsyncMock(return_value={}))
    monkeypatch.setattr(
        social.store,
        "create_draft",
        AsyncMock(return_value={"id": "post_1234567890123456", "status": "draft"}),
    )
    monkeypatch.setattr(
        social.store,
        "submit_draft",
        AsyncMock(return_value={"id": "post_1234567890123456", "status": "pending_approval"}),
    )
    monkeypatch.setattr(
        social.store,
        "request_approval",
        AsyncMock(return_value={"token": "a" * 24}),
    )
    monkeypatch.setattr(
        social.store,
        "decide_approval",
        AsyncMock(side_effect=lambda slug, tok, approve: {"id": "post_1234567890123456", "status": "scheduled" if approve else "draft"}),
    )
    main.app.dependency_overrides[main.owner_auth.current_user] = lambda: _owner_override("owner")
    try:
        client = TestClient(main.app)
        comp = client.post("/owner/social/compose", json={"content": "Dry run post", "account_ids": ["acct_1234567890123456"]})
        assert comp.status_code == 200
        created = client.post("/owner/social/posts", json={"content": "Dry run post", "account_ids": ["acct_1234567890123456"]})
        assert created.status_code == 200
        pid = created.json()["id"]
        sub = client.post(f"/owner/social/posts/{pid}/submit")
        assert sub.status_code == 200
        req = client.post(f"/owner/social/posts/{pid}/approval-request", json={"scheduled_at": 1900000000})
        assert req.status_code == 200
        tok = req.json()["token"]
        rej = client.post(f"/owner/social/approvals/{tok}/reject")
        assert rej.status_code == 200
        assert rej.json()["status"] == "draft"
    finally:
        main.app.dependency_overrides.clear()


def test_compose_does_not_force_disable_social_publish():
    compose_path = Path(__file__).resolve().parents[2] / "scripts" / "vps" / "compose.yml"
    text = compose_path.read_text(encoding="utf-8")
    assert 'SOCIAL_ENABLE_PUBLISH: "false"' not in text
