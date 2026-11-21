"""H6: post owner alerts to a Slack or Microsoft Teams incoming webhook (opt-in per tenant).

Off unless the tenant sets ``team_chat_webhook_url``. The URL must be https on a known Slack/Teams
host and is fetched through ``public_fetch.post_public`` (SSRF-safe, no redirects). Failures are
logged and never affect the alert that triggered them.
"""
import json
import logging
from urllib.parse import urlsplit

from . import automated_mail, flood_guard, public_fetch

log = logging.getLogger("concierge.team_chat")

_EXACT_HOSTS = {"hooks.slack.com", "outlook.office.com", "outlook.office365.com"}
_SUFFIX_HOSTS = (".webhook.office.com", ".logic.azure.com", ".powerplatform.com", ".api.powerplatform.com")


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return host in _EXACT_HOSTS or any(host.endswith(sfx) for sfx in _SUFFIX_HOSTS)


def validate_url(value):
    """None/blank passes through (clears the setting); otherwise a public https Slack/Teams URL."""
    if value is None or not value.strip():
        return value
    cleaned = value.strip()
    parts = public_fetch.validate_public_https_url(cleaned)
    if not _host_allowed(parts.hostname):
        raise ValueError("team chat webhook must be a Slack or Microsoft Teams incoming webhook URL")
    return cleaned


def payload_for(url: str, subject: str, body: str) -> dict:
    """Slack takes {text}; Teams/Power Automate accepts the same simple {text} message shape."""
    text = f"*{subject}*\n{body}" if urlsplit(url).hostname == "hooks.slack.com" else f"**{subject}**\n\n{body}"
    return {"text": text[:3000]}


async def notify(tenant: dict, subject: str, body: str) -> str:
    url = (tenant.get("team_chat_webhook_url") or "").strip()
    if not url:
        return "off"
    if not flood_guard.memory_allow("team_chat", tenant["slug"], 60, 3600):
        log.warning("team chat alert for %s dropped: more than 60 an hour", tenant["slug"])
        return "limited"
    subject = automated_mail.redact_security_codes(subject or "")
    body = automated_mail.redact_security_codes(body or "")
    try:
        validate_url(url)
        resp = await public_fetch.post_public(
            url, content=json.dumps(payload_for(url, subject, body)),
            headers={"Content-Type": "application/json"}, timeout=8.0)
        return "ok" if resp.is_success else f"http:{resp.status_code}"
    except Exception as exc:  # noqa: BLE001 - never let a chat webhook break the alert
        log.warning("team chat alert for %s failed: %s", tenant["slug"], type(exc).__name__)
        return "error"
