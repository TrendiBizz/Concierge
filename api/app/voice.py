"""Grok Voice Agent API helpers.

Flow: the browser asks us for a short-lived token, then opens the WebSocket to xAI directly
(browsers cannot send an Authorization header, so the token travels in the WebSocket
subprotocol). The long-lived XAI_API_KEY never leaves the server.
"""

import logging

import httpx

from . import db
from .config import get_settings
from .rag import build_system_prompt
from .tools import voice_tools

log = logging.getLogger("concierge.voice")


class VoiceUnavailable(RuntimeError):
    pass


def build_session(tenant: dict, *, website=False) -> dict:
    """Session config the widget sends as its first `session.update` event."""
    settings = get_settings()
    return {
        "voice": tenant.get("voice") or settings.voice_default,
        "instructions": build_system_prompt(tenant, None, channel="voice") + (
            "\nIf the caller asks for a text copy or recording link, save their contact and permission with capture_lead. Read back the saved recipient and requested format, wait for yes, then use request_conversation_copy. It arranges delivery after the conversation ends; never claim it was already sent. If recording is unavailable, offer saved text instead."
            if website else ""),
        "turn_detection": {"type": "server_vad"},
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transcription": {"model": "grok-transcribe"},
            },
            "output": {"format": {"type": "audio/pcm", "rate": 24000}},
        },
        "tools": voice_tools(tenant, website=website),
    }


def _extract_token(data: dict) -> str | None:
    # xAI's docs do not spell out the response shape, so accept the common variants.
    if isinstance(data.get("value"), str):
        return data["value"]
    secret = data.get("client_secret")
    if isinstance(secret, dict) and isinstance(secret.get("value"), str):
        return secret["value"]
    if isinstance(secret, str):
        return secret
    if isinstance(data.get("token"), str):
        return data["token"]
    return None


async def mint_token(tenant: dict) -> dict:
    settings = get_settings()
    if not settings.xai_api_key:
        raise VoiceUnavailable("XAI_API_KEY is not set")
    if not tenant["voice_enabled"]:
        raise VoiceUnavailable("Voice is disabled for this site")

    used = await db.pool().fetchval(
        "SELECT count(*) FROM voice_tokens WHERE tenant_id = $1 AND minted_at > now() - interval '1 day'",
        tenant["id"],
    )
    if used >= tenant["voice_daily_limit"]:
        raise VoiceUnavailable("Daily voice limit reached")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            settings.xai_client_secrets_url,
            headers={"Authorization": f"Bearer {settings.xai_api_key}"},
            json={"expires_after": {"seconds": settings.voice_token_ttl_seconds}},
        )
    if resp.status_code >= 400:
        log.error("xAI client_secrets failed: %s %s", resp.status_code, resp.text[:300])
        raise VoiceUnavailable("Voice service rejected the request")

    token = _extract_token(resp.json())
    if not token:
        log.error("Could not find a token in the xAI response keys: %s", list(resp.json().keys()))
        raise VoiceUnavailable("Voice service returned an unexpected response")

    await db.pool().execute("INSERT INTO voice_tokens (tenant_id) VALUES ($1)", tenant["id"])
    return {
        "token": token,
        "url": settings.voice_ws_url,
        "session": build_session(tenant, website=True),
    }
