"""Website chatbot microphone on OpenAI Realtime (WEB_VOICE_PROVIDER=openai_realtime). Default stays Gemini."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import voice
from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tenant(**kw):
    base = {"id": 1, "slug": "t", "name": "Test Plumbing", "voice_enabled": True, "voice_daily_limit": 20,
            "voice": None, "website_url": "https://example.test", "business_hours": "9-5"}
    base.update(kw)
    return base


class _Client:
    captured = {}
    status = 200
    payload = {"value": "ek_test_secret", "expires_at": 1}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None, **kw):
        _Client.captured = {"url": url, "json": json, "headers": headers}
        cls = _Client
        return SimpleNamespace(status_code=cls.status, text="", json=lambda: cls.payload)


def _setup(monkeypatch, **settings):
    pool = SimpleNamespace(fetchval=AsyncMock(return_value=0), execute=AsyncMock())
    monkeypatch.setattr(voice.db, "pool", lambda: pool)
    monkeypatch.setattr(voice.httpx, "AsyncClient", _Client)
    _Client.status, _Client.payload = 200, {"value": "ek_test_secret", "expires_at": 1}
    monkeypatch.setattr(voice, "get_settings", lambda: Settings(_env_file=None, **settings))
    return pool


def test_openai_web_token_locks_session_server_side(monkeypatch):
    pool = _setup(monkeypatch, web_voice_provider="openai_realtime", openai_api_key="sk-test")
    result = asyncio.run(voice.mint_token(_tenant()))
    assert result["provider"] == "openai_realtime"
    assert result["token"] == "ek_test_secret"
    assert result["url"] == "wss://api.openai.com/v1/realtime"
    sent = _Client.captured
    assert sent["url"].endswith("/v1/realtime/client_secrets")
    assert sent["headers"] == {"Authorization": "Bearer sk-test"}
    sess = sent["json"]["session"]
    assert sess["type"] == "realtime" and sess["model"] == "gpt-realtime"
    assert sess["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert sess["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    # Same tool set and prompt the Gemini web path gets.
    expected = voice.build_session(_tenant(), website=True)
    assert sess["instructions"] == expected["instructions"]
    assert {t["name"] for t in sess["tools"]} == {t["name"] for t in expected["tools"]}
    assert "capture_lead" in {t["name"] for t in sess["tools"]}
    assert "sk-test" not in str(result)
    pool.execute.assert_awaited_once()


def test_openai_web_token_limits_and_errors(monkeypatch):
    _setup(monkeypatch, web_voice_provider="openai_realtime", openai_api_key="")
    with pytest.raises(voice.VoiceUnavailable, match="OPENAI_API_KEY"):
        asyncio.run(voice.mint_token(_tenant()))
    pool = _setup(monkeypatch, web_voice_provider="openai_realtime", openai_api_key="k")
    with pytest.raises(voice.VoiceUnavailable, match="disabled"):
        asyncio.run(voice.mint_token(_tenant(voice_enabled=False)))
    pool.fetchval.return_value = 20
    with pytest.raises(voice.VoiceUnavailable, match="limit"):
        asyncio.run(voice.mint_token(_tenant(voice_daily_limit=20)))
    pool.fetchval.return_value = 0
    _Client.status = 429
    with pytest.raises(voice.VoiceUnavailable, match="rejected"):
        asyncio.run(voice.mint_token(_tenant()))
    _Client.status, _Client.payload = 200, {}
    with pytest.raises(voice.VoiceUnavailable, match="unexpected"):
        asyncio.run(voice.mint_token(_tenant()))
    pool.execute.assert_not_awaited()


def test_default_web_provider_is_still_gemini(monkeypatch):
    _setup(monkeypatch, gemini_api_key="g")
    _Client.payload = {"name": "auth_tokens/x"}
    result = asyncio.run(voice.mint_token(_tenant()))
    assert result["provider"] == "gemini_live"
    assert "BidiGenerateContentConstrained" in result["url"]


def test_widget_and_csp_support_openai_web_voice():
    widget = (REPO_ROOT / "api" / "static" / "widget.js").read_text(encoding="utf-8")
    for needle in ("openai-insecure-api-key.", "input_audio_buffer.append", "response.output_audio.delta",
                   "conversation.item.input_audio_transcription.completed", "function_call_output",
                   "input_audio_buffer.speech_started"):
        assert needle in widget
    assert "access_token=" in widget  # Gemini path untouched
    from app import security
    assert "wss://api.openai.com" in security.DEMO_CSP
    assert "wss://api.openai.com" in (REPO_ROOT / "website" / "_headers").read_text(encoding="utf-8")
