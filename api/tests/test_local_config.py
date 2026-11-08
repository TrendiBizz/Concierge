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
    ("http://127.0.0.1:4390", True), ("http://host.docker.internal:4391", True),
    ("http://localhost:4391", True), ("http://attacker.test:4391", False),
    ("https://localhost:4391", False), ("http://localhost:80", False),
    ("http://localhost:4391/path", False), ("http://localhost:4391?x=y", False),
    ("http://user:pass@localhost:4391", False),
])
def test_social_backend_stays_private_with_separate_local_port(monkeypatch, url, permitted):
    config = Settings(_env_file=None, social_service_enabled=True,
                      social_service_url=url, social_concierge_key="x" * 40)
    monkeypatch.setattr(social_bridge, "get_settings", lambda: config)
    if permitted:
        assert social_bridge._configuration() == (url, "x" * 40)
    else:
        with pytest.raises(HTTPException):
            social_bridge._configuration()


def test_x_oauth_bridge_keeps_tenant_and_validates_callback(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    calls = []

    async def ensure(tenant):
        assert tenant == {"slug": "business-a"}
        return tenant["slug"]

    async def request(method, path, data=None):
        calls.append((method, path, data))
        return {"ok": True}

    monkeypatch.setattr(social_bridge, "ensure_tenant", ensure)
    monkeypatch.setattr(social_bridge, "_request", request)
    tenant = {"slug": "business-a"}
    state = "a" * 32
    asyncio.run(social_bridge.start_x_oauth(tenant))
    asyncio.run(social_bridge.finish_x_oauth(tenant, state, "provider-code"))
    assert calls == [("POST", "/v1/customers/business-a/oauth/x/start", None),
                     ("POST", "/v1/customers/business-a/oauth/x/finish", {"state": state, "code": "provider-code"})]
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
