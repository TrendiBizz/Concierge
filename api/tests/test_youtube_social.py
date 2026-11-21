"""YouTube integration contracts with synthetic identities and mock transports only."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from app import owner_auth, social_bridge
from app.main import app

TENANT = {"slug": "test-business", "name": "Test business", "role": "owner"}
IDENTIFIER = "m" * 32


def test_bridge_forwards_tenant_scoped_start_finish_disconnect():
    async def run():
        with patch.object(social_bridge, "ensure_tenant", AsyncMock(return_value=TENANT["slug"])) as ensure, patch.object(social_bridge, "_request", AsyncMock(return_value={})) as request:
            await social_bridge.start_youtube_oauth(TENANT)
            await social_bridge.finish_youtube_oauth(TENANT, IDENTIFIER, "mock-code")
            await social_bridge.disconnect_youtube(TENANT, IDENTIFIER)
            assert [call.args[:2] for call in request.await_args_list] == [
                ("POST", "/v1/customers/test-business/oauth/youtube/start"),
                ("POST", "/v1/customers/test-business/oauth/youtube/finish"),
                ("DELETE", "/v1/customers/test-business/oauth/youtube/accounts/" + IDENTIFIER)]
            assert request.await_args_list[1].args[2] == {"state": IDENTIFIER, "code": "mock-code"}
            assert ensure.await_count == 3
    asyncio.run(run())


@pytest.mark.parametrize("state,code", [("bad", "mock-code"), (IDENTIFIER, ""), (IDENTIFIER, "x" * 2049)])
def test_invalid_callback_does_not_provision_or_call_backend(state, code):
    async def run():
        with patch.object(social_bridge, "ensure_tenant", AsyncMock()) as ensure:
            with pytest.raises(HTTPException) as error:
                await social_bridge.finish_youtube_oauth(TENANT, state, code)
            assert error.value.status_code == 400
            ensure.assert_not_awaited()
    asyncio.run(run())


def test_invalid_disconnect_is_rejected_locally():
    async def run():
        with patch.object(social_bridge, "ensure_tenant", AsyncMock()) as ensure:
            with pytest.raises(HTTPException):
                await social_bridge.disconnect_youtube(TENANT, "../other")
            ensure.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("role,expected", [("owner", 200), ("editor", 403), ("viewer", 403)])
def test_routes_require_owner_and_preserve_tenant(role, expected):
    async def run():
        tenant = dict(TENANT, role=role)
        async def current_user():
            return tenant
        app.dependency_overrides[owner_auth.current_user] = current_user
        try:
            with patch.object(social_bridge, "start_youtube_oauth", AsyncMock(return_value={})) as start, patch.object(social_bridge, "finish_youtube_oauth", AsyncMock(return_value={})) as finish, patch.object(social_bridge, "disconnect_youtube", AsyncMock(return_value={})) as disconnect:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    results = [await client.post("/owner/social/oauth/youtube/start"), await client.post("/owner/social/oauth/youtube/finish", json={"state": IDENTIFIER, "code": "mock-code"}), await client.delete("/owner/social/oauth/youtube/accounts/" + IDENTIFIER)]
                assert [r.status_code for r in results] == [expected] * 3
                for call in [start, finish, disconnect]:
                    if role == "owner":
                        assert call.await_args.args[0] == tenant
                    else:
                        call.assert_not_awaited()
        finally:
            app.dependency_overrides.clear()
    asyncio.run(run())


def test_status_reports_only_youtube_readiness_boolean():
    async def run():
        async def current_user():
            return TENANT
        app.dependency_overrides[owner_auth.current_user] = current_user
        try:
            with patch("app.main.settings", SimpleNamespace(social_service_enabled=True)), patch.object(social_bridge, "provider_status", AsyncMock(return_value={"youtube": True, "unexpected": "must-not-return"})):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    response = await client.get("/owner/social/status")
                assert response.json()["providers"]["youtube"] is True
                assert "must-not-return" not in response.text
        finally:
            app.dependency_overrides.clear()
    asyncio.run(run())


@pytest.mark.parametrize("detail,expected", [("YouTube did not grant upload access", "YouTube did not grant upload access"), ("untrusted provider detail", "Social request could not be completed")])
def test_bridge_only_exposes_allowlisted_errors(detail, expected):
    async def run():
        response = httpx.Response(400, json={"error": detail}, request=httpx.Request("POST", "http://testserver"))
        client = AsyncMock()
        client.request.return_value = response
        with patch.object(social_bridge, "_configuration", return_value=("http://127.0.0.1:4390", "mock-only")), patch("app.flood_guard.memory_allow", return_value=True), patch.object(httpx, "AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            with pytest.raises(HTTPException) as error:
                await social_bridge._request("POST", "/v1/customers/test-business/oauth/youtube/finish", {})
            assert error.value.detail == expected
    asyncio.run(run())


def test_owner_and_portal_offer_youtube_and_private_review_fields():
    root = Path(__file__).resolve().parents[2]
    owner = (root / "api/static/owner.html").read_text()
    assert 'id="social-youtube-connect"' in owner
    assert 'startSocialOAuth("youtube")' in owner
    assert 'options.privacy="private"' in owner
    assert 'options.description=edit.value' in owner
    assert 'title.reportValidity()' in owner
    assert 'new TextEncoder().encode(options.description).length>5000' in owner
    assert 'YouTube channel disconnected.' in owner
    assert "id: 'youtube'" in (root / "web/portal/src/SocialIcon.tsx").read_text()
    assert (root / "web/portal/public/social/youtube.svg").is_file()
