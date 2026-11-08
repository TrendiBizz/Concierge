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
