#!/usr/bin/env python3
"""Verify Google Gemini 3.8 Live API connectivity (direct WS + ephemeral browser token).

Never prints the API key or places any phone call.
Usage: GEMINI_API_KEY=... python3 scripts/vps/check-gemini-voice.py
"""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import urllib.request

import websockets


async def check_direct_ws(api_key: str, model: str, ws_base: str) -> None:
    sep = "&" if "?" in ws_base else "?"
    url = f"{ws_base}{sep}key={api_key}"
    payload = {
        "setup": {
            "model": model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Aoede"}}},
            },
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
    }
    async with websockets.connect(url, open_timeout=15) as ws:
        await ws.send(json.dumps(payload))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        if "setupComplete" not in msg:
            raise RuntimeError(f"Expected setupComplete, got: {list(msg.keys())}")


def check_ephemeral_token(api_key: str, model: str, tokens_url: str) -> str:
    now = datetime.now(timezone.utc)
    body = json.dumps({
        "uses": 1,
        "expireTime": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "newSessionExpireTime": (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "bidiGenerateContentSetup": {
            "model": model,
            "generationConfig": {"responseModalities": ["AUDIO"]},
        },
    }).encode()
    sep = "&" if "?" in tokens_url else "?"
    req = urllib.request.Request(
        f"{tokens_url}{sep}key={api_key}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"Unexpected auth_tokens response keys: {list(data.keys())}")
    return name


async def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("FAIL: GEMINI_API_KEY is not set", file=sys.stderr)
        return 1
    model = os.environ.get("GEMINI_LIVE_MODEL", "models/gemini-3.8-live")
    ws_base = os.environ.get(
        "GEMINI_LIVE_WS_URL",
        "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent",
    )
    tokens_url = os.environ.get(
        "GEMINI_AUTH_TOKENS_URL",
        "https://generativelanguage.googleapis.com/v1alpha/auth_tokens",
    )
    await check_direct_ws(api_key, model, ws_base)
    print(f"OK: direct Gemini Live WS handshake succeeded ({model})")
    token = check_ephemeral_token(api_key, model, tokens_url)
    print(f"OK: ephemeral browser auth token minted ({token[:16]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
