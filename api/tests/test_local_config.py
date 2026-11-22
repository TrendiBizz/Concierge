import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings
from app import social_bridge


@pytest.mark.parametrize("url", [
    "https://concierge.trendibizz.com/owner-ui",
    "http://127.0.0.1:8793/owner-ui", "http://localhost:8793/owner-ui",
    "http://[::1]:8793/owner-ui",
])
def test_invitation_origin_accepts_https_or_loopback(url):
    assert Settings(_env_file=None, owner_portal_url=url).owner_portal_url == url


@pytest.mark.parametrize("url", [
    "http://example.com/owner-ui", "http://127.0.0.1.attacker.test/owner-ui",
    "http://0.0.0.0:8793/owner-ui", "http://192.168.1.1/owner-ui",
    "http://user:pass@localhost/owner-ui", "http://localhost/owner-ui?token=x",
    "http://localhost/owner-ui#invite=x", "http://localhost/admin-ui",
])
def test_invitation_origin_rejects_unsafe_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, owner_portal_url=url)


@pytest.mark.parametrize("url,permitted", [
    ("https://concierge.trendibizz.com/owner/social/oauth/callback", True),
    ("http://127.0.0.1:8000/owner/social/oauth/callback", True),
    ("http://localhost:8000/owner/social/oauth/callback", True),
    ("http://attacker.test/owner/social/oauth/callback", False),
    ("https://concierge.trendibizz.com/wrong-path", False),
    ("https://concierge.trendibizz.com/owner/social/oauth/callback?x=y", False),
    ("https://user:pass@concierge.trendibizz.com/owner/social/oauth/callback", False),
])
def test_social_oauth_callback_url_validation(url, permitted):
    from app.social import config as social_config
    res = social_config.validated_callback(url)
    assert (res == url) if permitted else (res is None)


def test_x_oauth_bridge_keeps_tenant_and_validates_callback(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from app import social
    calls = []

    async def ensure(tenant):
        assert tenant == {"slug": "business-a"}
        return tenant["slug"]

    async def fake_start(slug, network):
        calls.append(("start", slug, network))
        return {"authorization_url": "https://x.com/i/oauth2/authorize?state=s", "state": "a" * 32}

    async def fake_finish(slug, network, state, code):
        if len(state) < 32:
            raise HTTPException(400, "Invalid OAuth callback")
        calls.append(("finish", slug, network, state, code))
        return {"ok": True}

    monkeypatch.setattr(social_bridge, "ensure_tenant", ensure)
    monkeypatch.setattr(social.oauth, "start_oauth", fake_start)
    monkeypatch.setattr(social.oauth, "finish_oauth", fake_finish)
    tenant = {"slug": "business-a"}
    state = "a" * 32
    asyncio.run(social_bridge.start_x_oauth(tenant))
    asyncio.run(social_bridge.finish_x_oauth(tenant, state, "provider-code"))
    assert calls == [
        ("start", "business-a", "x"),
        ("finish", "business-a", "x", state, "provider-code"),
    ]
    with pytest.raises(HTTPException):
        asyncio.run(social_bridge.finish_x_oauth(tenant, "bad", "provider-code"))
    assert len(calls) == 2


def test_website_verification_requires_tenant_match_and_actual_credentials():
    from app.owner_onboarding import website_channel_status
    tenant = {"slug": "a", "site_url": "https://example.org", "voice_enabled": True}
    s = Settings(_env_file=None, xai_api_key="fixture", website_verified_tenants="a")
    assert website_channel_status(tenant, s)["website_voice"] == {"configured": True, "verified": True}
    assert website_channel_status({**tenant, "slug": "b"}, s)["website_voice"]["verified"] is False
    assert website_channel_status({**tenant, "voice_enabled": False}, s)["website_voice"]["configured"] is False
    missing = Settings(_env_file=None, website_verified_tenants="a")
    assert website_channel_status(tenant, missing)["website_voice"] == {"configured": False, "verified": False}
