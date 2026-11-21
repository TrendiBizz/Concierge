"""Regression tests for PR 1 audit security, auth, and RBAC fixes."""

from __future__ import annotations

import asyncio
import base64
import inspect
import os

import pytest
from fastapi.testclient import TestClient

from app import (
    chat_inbox,
    db,
    integrations,
    media_studio,
    owner_auth,
    sms_inbox,
    tenant_pause,
    tenants,
)
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL", "")
ADMIN = {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "test-admin-token")}


def test_admin_pending_invites_requires_admin_auth(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-audit-token")
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        resp = client.get("/admin/pending-invites")
        assert resp.status_code == 401
    finally:
        get_settings.cache_clear()


def test_svg_logo_rejected_by_parser():
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)></svg>").decode()
    with pytest.raises(ValueError):
        media_studio.parse_logo_data_uri(svg)

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    png = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    mime, raw = media_studio.parse_logo_data_uri(png)
    assert mime == "image/png"
    assert raw == png_bytes


def test_integrations_key_fails_closed_without_secret(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(Exception) as exc:
            integrations._key()
        assert getattr(exc.value, "status_code", None) == 503
    finally:
        get_settings.cache_clear()


def test_takeover_and_live_calls_require_editor():
    assert 'require_role(user, "editor")' in inspect.getsource(chat_inbox.takeover)
    assert 'require_role(user, "editor")' in inspect.getsource(sms_inbox.takeover)
    from app.routers import telephony
    assert 'require_role(user, "editor")' in inspect.getsource(telephony.owner_live_supervise)
    assert 'require_role(user, "editor")' in inspect.getsource(telephony.owner_live_supervise_stop)
    assert 'require_role(user, "editor")' in inspect.getsource(telephony.owner_live_takeover)


def test_studio_static_uses_is_relative_to():
    from app.routers import public
    assert "is_relative_to" in inspect.getsource(public.studio_asset)
    assert "is_relative_to" in inspect.getsource(public.studio_file)


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_billing_pause_cannot_be_unpaused_by_owner(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("DATABASE_URL", DSN)
    get_settings.cache_clear()

    async def _run():
        await db.init()
        slug = f"audit-billpause-{os.getpid()}"
        try:
            t = await tenants.create(name="BillPause Co", slug=slug, site_url="https://example.com")
            await tenant_pause.set_paused(t["id"], True, "billing")
            from app.routers.owner_portal import PauseRequest, owner_set_pause
            user = {"tenant_id": t["id"], "role": "owner", "email": "owner@example.com"}
            with pytest.raises(Exception) as exc:
                await owner_set_pause(PauseRequest(paused=False), user=user)
            assert getattr(exc.value, "status_code", None) == 402
            state = await tenant_pause.state(t["id"])
            assert state["paused"] is True
            assert state["by"] == "billing"
        finally:
            await db.pool().execute("DELETE FROM tenants WHERE slug=$1", slug)
            await db.close()

    try:
        asyncio.run(_run())
    finally:
        get_settings.cache_clear()


@pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")
def test_deactivated_member_cannot_self_reactivate_and_grace_does_not_reset(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("DATABASE_URL", DSN)
    get_settings.cache_clear()

    async def _run():
        await db.init()
        slug = f"audit-deact-{os.getpid()}"
        try:
            t = await tenants.create(name="Deact Co", slug=slug, site_url="https://example.com")
            owner_tok = await owner_auth.make_invite(t["id"], "boss@example.com", "owner")
            await owner_auth.accept_invite(owner_tok)
            owner_row = await db.pool().fetchrow(
                "SELECT id, email, role FROM tenant_users WHERE tenant_id=$1 AND email='boss@example.com'",
                t["id"],
            )

            # Invite a staff member, let them sign in, and mint a recovery/install ticket
            staff_tok = await owner_auth.make_invite(t["id"], "staff@example.com", "editor")
            await owner_auth.accept_invite(staff_tok)
            # Verify grace window preserves first used_at timestamp
            first_used = await db.pool().fetchval(
                "SELECT used_at FROM tenant_invites WHERE token_hash=$1", owner_auth.digest(staff_tok))
            assert first_used is not None
            await owner_auth.accept_invite(staff_tok)
            second_used = await db.pool().fetchval(
                "SELECT used_at FROM tenant_invites WHERE token_hash=$1", owner_auth.digest(staff_tok))
            assert second_used == first_used

            install_tok = await owner_auth.make_install_ticket(t["id"], "staff@example.com", "editor")
            staff_row = await db.pool().fetchrow(
                "SELECT id FROM tenant_users WHERE tenant_id=$1 AND email='staff@example.com'", t["id"])

            # Deactivate staff member
            from app.routers.owner_portal import owner_team_deactivate
            await owner_team_deactivate(
                staff_row["id"],
                user={"id": owner_row["id"], "tenant_id": t["id"], "role": "owner", "email": "boss@example.com"},
            )

            # Outstanding install ticket must be deleted and rejected
            with pytest.raises(ValueError):
                await owner_auth.accept_invite(install_tok)
        finally:
            await db.pool().execute("DELETE FROM tenants WHERE slug=$1", slug)
            await db.close()

    try:
        asyncio.run(_run())
    finally:
        get_settings.cache_clear()
