"""Google Gemini 3.8 Live API helpers for website and telephone voice.

Flow (website): the browser asks us for a single-use ephemeral token (`v1alpha/auth_tokens`)
with the session's model, system instructions and tools locked server-side, then connects
directly to `BidiGenerateContentConstrained?access_token=<token>`. The long-lived
`GEMINI_API_KEY` never leaves the server.
"""

from datetime import datetime, timedelta, timezone
import logging

import httpx

from . import db
from .config import get_settings
from .rag import build_system_prompt
from .tools import voice_tools

log = logging.getLogger("concierge.voice")

GEMINI_VOICES = frozenset({
    "Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Zephyr",
})


class VoiceUnavailable(RuntimeError):
    pass


COPY_DELIVERY_INSTRUCTIONS = (
    "\nIf the caller asks for a text copy or recording link, save their contact and permission with capture_lead. Read back the saved recipient and requested format, wait for yes, then use request_conversation_copy. It arranges delivery after the conversation ends; never claim it was already sent. If recording is unavailable, offer saved text instead."
)


def strip_additional_properties(schema):
    """Recursively strip 'additionalProperties' keys that Gemini Live rejects."""
    if isinstance(schema, dict):
        return {
            k: strip_additional_properties(v)
            for k, v in schema.items()
            if k != "additionalProperties"
        }
    if isinstance(schema, list):
        return [strip_additional_properties(item) for item in schema]
    return schema


def gemini_function_declarations(tools) -> list[dict]:
    """Convert flat tool specs into Gemini Live `functionDeclarations`."""
    declarations = []
    for tool in tools or ():
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        decl = {
            "name": tool["name"],
            "description": tool.get("description", ""),
        }
        params = strip_additional_properties(tool.get("parameters"))
        if isinstance(params, dict) and params.get("properties"):
            decl["parameters"] = params
        declarations.append(decl)
    return declarations


def resolve_voice_name(requested: str | None, fallback: str | None = None) -> str:
    if requested in GEMINI_VOICES:
        return requested
    if fallback in GEMINI_VOICES:
        return fallback
    return "Aoede"


def build_session(tenant: dict, *, website=False, copy_delivery=False) -> dict:
    """Build the Gemini Live voice session descriptor shared by website voice and telephony."""
    settings = get_settings()
    can_deliver = website or copy_delivery
    voice_name = resolve_voice_name(tenant.get("voice"), settings.gemini_live_voice or settings.voice_default)
    return {
        "model": settings.gemini_live_model,
        "voice": voice_name,
        "gemini_voice": voice_name,
        "thinking_level": settings.gemini_thinking_level,
        "instructions": build_system_prompt(tenant, None, channel="voice") + (
            COPY_DELIVERY_INSTRUCTIONS if can_deliver else ""),
        "tools": voice_tools(tenant, website=can_deliver),
    }


def build_gemini_setup(session: dict, *, silence_duration_ms: int | None = None,
                       prefix_padding_ms: int | None = None) -> dict:
    """Build a Gemini Live `BidiGenerateContentSetup` object from a session dict."""
    settings = get_settings()
    voice_name = resolve_voice_name(
        session.get("gemini_voice") or session.get("voice"),
        settings.gemini_live_voice or settings.voice_default,
    )
    generation_config: dict = {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": voice_name},
            },
        },
    }
    thinking_level = session.get("thinking_level") or settings.gemini_thinking_level
    if thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}

    realtime_input: dict = {
        "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
    }
    if silence_duration_ms is not None or prefix_padding_ms is not None:
        vad: dict = {}
        if prefix_padding_ms is not None:
            vad["prefixPaddingMs"] = prefix_padding_ms
        if silence_duration_ms is not None:
            vad["silenceDurationMs"] = silence_duration_ms
        realtime_input["automaticActivityDetection"] = vad

    setup: dict = {
        "model": session.get("model") or settings.gemini_live_model,
        "generationConfig": generation_config,
        "realtimeInputConfig": realtime_input,
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "contextWindowCompression": {"slidingWindow": {}},
    }
    instructions = session.get("instructions")
    if instructions:
        setup["systemInstruction"] = {"parts": [{"text": instructions}]}
    declarations = gemini_function_declarations(session.get("tools"))
    if declarations:
        setup["tools"] = [{"functionDeclarations": declarations}]
    return setup


def _extract_token(data: dict) -> str | None:
    """Extract the ephemeral token name returned by Google's `v1alpha/auth_tokens`."""
    if isinstance(data.get("name"), str) and data["name"].strip():
        return data["name"].strip()
    if isinstance(data.get("token"), str) and data["token"].strip():
        return data["token"].strip()
    return None


async def mint_token(tenant: dict) -> dict:
    settings = get_settings()
    openai_web = settings.web_voice_provider == "openai_realtime"
    if openai_web and not settings.openai_api_key.strip():
        raise VoiceUnavailable("OPENAI_API_KEY is not set")
    if not openai_web and not settings.gemini_api_key:
        raise VoiceUnavailable("GEMINI_API_KEY is not set")
    if not tenant["voice_enabled"]:
        raise VoiceUnavailable("Voice is disabled for this site")

    used = await db.pool().fetchval(
        "SELECT count(*) FROM voice_tokens WHERE tenant_id = $1 AND minted_at > now() - interval '1 day'",
        tenant["id"],
    )
    if used >= tenant["voice_daily_limit"]:
        raise VoiceUnavailable("Daily voice limit reached")

    session = build_session(tenant, website=True)
    if openai_web:
        return await _mint_openai_token(tenant, session, settings)
    setup = build_gemini_setup(session)
    ttl = max(60, int(settings.voice_token_ttl_seconds))
    now = datetime.now(timezone.utc)
    expire_time = (now + timedelta(seconds=max(ttl, 600))).isoformat().replace("+00:00", "Z")
    new_session_expire = (now + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            settings.gemini_auth_tokens_endpoint,
            json={
                "uses": 1,
                "expireTime": expire_time,
                "newSessionExpireTime": new_session_expire,
                "bidiGenerateContentSetup": setup,
            },
        )
    if resp.status_code >= 400:
        log.error("Gemini auth_tokens failed: %s %s", resp.status_code, resp.text[:300])
        raise VoiceUnavailable("Voice service rejected the request")

    token = _extract_token(resp.json())
    if not token:
        log.error("Could not find a token in the Gemini auth_tokens response keys: %s", list(resp.json().keys()))
        raise VoiceUnavailable("Voice service returned an unexpected response")

    await db.pool().execute("INSERT INTO voice_tokens (tenant_id) VALUES ($1)", tenant["id"])
    return {
        "provider": "gemini_live",
        "token": token,
        "url": settings.gemini_constrained_ws_url,
        "model": session["model"],
        "session": session,
    }


async def _mint_openai_token(tenant: dict, session: dict, settings) -> dict:
    """OpenAI Realtime client secret for the website mic. Same limits, tools and tenant lock as Gemini."""
    from . import voice_openai
    ttl = max(60, int(settings.voice_token_ttl_seconds))
    voice = tenant.get("voice")
    session = {**session, "model": settings.openai_realtime_model,
               "voice": voice if voice in voice_openai.OPENAI_VOICES else settings.openai_realtime_voice}
    body = voice_openai.web_client_secret_body(
        session, ttl_seconds=ttl, transcribe_model=settings.openai_realtime_transcribe_model,
        turn=settings.openai_turn_detection)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.openai_client_secrets_url, json=body,
                                 headers={"Authorization": f"Bearer {settings.openai_api_key.strip()}"})
    if resp.status_code >= 400:
        log.error("OpenAI client_secrets failed: %s %s", resp.status_code, resp.text[:300])
        raise VoiceUnavailable("Voice service rejected the request")
    data = resp.json()
    token = data.get("value") if isinstance(data.get("value"), str) else None
    if not token:
        log.error("No client secret in OpenAI response keys: %s", list(data.keys()))
        raise VoiceUnavailable("Voice service returned an unexpected response")
    await db.pool().execute("INSERT INTO voice_tokens (tenant_id) VALUES ($1)", tenant["id"])
    return {"provider": "openai_realtime", "token": token, "url": settings.openai_realtime_ws_url,
            "model": session["model"], "session": session}
