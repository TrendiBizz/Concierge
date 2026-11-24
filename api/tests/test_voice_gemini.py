"""Tests for Google Gemini 3.8 Live browser voice and zero-xAI/Grok regression guards."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import voice
from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tenant(**over):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "slug": "alpha",
        "name": "Alpha Services",
        "voice": "Aoede",
        "voice_enabled": True,
        "voice_daily_limit": 20,
        "native_booking": False,
        "booking_url": "",
    }
    base.update(over)
    return base


def test_build_session_and_gemini_setup_use_gemini_3_8_live_protocol():
    session = voice.build_session(_tenant(voice="invalid-legacy-voice"), website=True)
    assert session["model"] == "models/gemini-3.8-live"
    assert session["voice"] == "Aoede"
    assert session["tools"]

    setup = voice.build_gemini_setup(session)
    assert setup["model"] == "models/gemini-3.8-live"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Aoede"
    assert "thinkingConfig" not in setup["generationConfig"]
    assert setup["realtimeInputConfig"]["activityHandling"] == "START_OF_ACTIVITY_INTERRUPTS"
    assert setup["inputAudioTranscription"] == {}
    assert setup["outputAudioTranscription"] == {}
    assert setup["systemInstruction"]["parts"][0]["text"]
    decls = setup["tools"][0]["functionDeclarations"]
    assert decls
    for d in decls:
        if "parameters" in d:
            assert "additionalProperties" not in str(d["parameters"])


def test_mint_token_mints_single_use_gemini_ephemeral_token(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"name": "auth_tokens/ephemeral-test-token"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    pool = SimpleNamespace(fetchval=AsyncMock(return_value=0), execute=AsyncMock())
    monkeypatch.setattr(voice.db, "pool", lambda: pool)
    monkeypatch.setattr(voice.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        voice,
        "get_settings",
        lambda: Settings(_env_file=None, gemini_api_key="test-gemini-key"),
    )

    result = asyncio.run(voice.mint_token(_tenant()))
    assert result["token"] == "auth_tokens/ephemeral-test-token"
    assert "BidiGenerateContentConstrained" in result["url"]
    assert result["model"] == "models/gemini-3.8-live"
    assert "v1alpha/auth_tokens?key=test-gemini-key" in captured["url"]
    assert captured["json"]["uses"] == 1
    assert captured["json"]["bidiGenerateContentSetup"]["model"] == "models/gemini-3.8-live"
    assert "thinkingConfig" not in captured["json"]["bidiGenerateContentSetup"]["generationConfig"]
    pool.execute.assert_awaited_once()


def test_mint_token_requires_gemini_key_and_enforces_limits(monkeypatch):
    monkeypatch.setattr(voice, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=""))
    with pytest.raises(voice.VoiceUnavailable, match="GEMINI_API_KEY"):
        asyncio.run(voice.mint_token(_tenant()))

    monkeypatch.setattr(voice, "get_settings", lambda: Settings(_env_file=None, gemini_api_key="k"))
    with pytest.raises(voice.VoiceUnavailable, match="disabled"):
        asyncio.run(voice.mint_token(_tenant(voice_enabled=False)))

    pool = SimpleNamespace(fetchval=AsyncMock(return_value=20), execute=AsyncMock())
    monkeypatch.setattr(voice.db, "pool", lambda: pool)
    with pytest.raises(voice.VoiceUnavailable, match="limit"):
        asyncio.run(voice.mint_token(_tenant(voice_daily_limit=20)))


def test_widget_and_csp_use_gemini_live_and_never_xai():
    widget = (REPO_ROOT / "api" / "static" / "widget.js").read_text(encoding="utf-8")
    assert "access_token=" in widget
    assert "audio/pcm;rate=16000" in widget
    assert "realtimeInput" in widget
    assert "toolResponse" in widget
    assert "setupComplete" in widget
    assert "xai-client-secret" not in widget.lower()
    assert "api.x.ai" not in widget.lower()

    headers = (REPO_ROOT / "website" / "_headers").read_text(encoding="utf-8")
    assert "wss://generativelanguage.googleapis.com" in headers
    assert "api.x.ai" not in headers

    from app import security
    assert "wss://generativelanguage.googleapis.com" in security.DEMO_CSP
    assert "api.x.ai" not in security.DEMO_CSP


def test_no_xai_or_grok_code_remains_in_runtime_app():
    app_dir = REPO_ROOT / "api" / "app"
    hits = []
    for path in sorted(app_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if "xai" in low or "grok" in low or "api.x.ai" in low:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not hits, "xAI/Grok references must not remain in api/app:\n" + "\n".join(hits)
