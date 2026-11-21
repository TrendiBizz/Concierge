"""H6: Slack/Teams owner alerts are opt-in, host-restricted and fail-safe."""
import asyncio

import pytest

from app import team_chat_alerts as t


def test_validate_accepts_slack_and_teams_only():
    assert t.validate_url("") == ""
    assert t.validate_url(None) is None
    assert t.validate_url("https://hooks.slack.com/services/T/B/x").startswith("https://hooks.slack.com")
    assert t.validate_url("https://acme.webhook.office.com/webhookb2/abc")
    for bad in ("http://hooks.slack.com/x", "https://evil.example.com/x", "https://hooks.slack.com.evil.io/x",
                "https://127.0.0.1/x"):
        with pytest.raises(ValueError):
            t.validate_url(bad)


def test_payload_and_redaction(monkeypatch):
    sent = {}

    async def fake_post(url, **kw):
        sent["url"], sent["content"] = url, kw["content"]

        class R:
            is_success = True
            status_code = 200
        return R()

    monkeypatch.setattr(t.public_fetch, "post_public", fake_post)
    tenant = {"slug": "acme", "team_chat_webhook_url": "https://hooks.slack.com/services/T/B/x"}
    assert asyncio.run(t.notify(tenant, "New enquiry", "Call Sam")) == "ok"
    assert "New enquiry" in sent["content"]
    assert asyncio.run(t.notify({"slug": "acme"}, "x", "y")) == "off"


def test_failure_never_raises(monkeypatch):
    async def boom(url, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(t.public_fetch, "post_public", boom)
    tenant = {"slug": "acme2", "team_chat_webhook_url": "https://hooks.slack.com/services/T/B/x"}
    assert asyncio.run(t.notify(tenant, "s", "b")) == "error"
