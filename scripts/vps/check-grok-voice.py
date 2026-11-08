"""Run inside the API container; exercise public voice auth and real Grok audio.

Usage on VPS: docker exec -i trendi-api-1 python - < this-file.py
No microphone, telephone call, outbound message or long-lived credential output.
"""
import asyncio
import json
import os
import uuid

import asyncpg
import httpx
import websockets

from app.config import get_settings


async def main():
    settings = get_settings()
    connection = await asyncpg.connect(settings.database_url)
    try:
        tenant = await connection.fetchrow(
            "SELECT public_key,voice_enabled FROM tenants WHERE slug=$1",
            os.environ.get("VOICE_CHECK_TENANT", "trendi-oauth-staging"),
        )
    finally:
        await connection.close()
    assert tenant and tenant["voice_enabled"], "FAIL tenant voice is disabled"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://chat.trendibizz.com/api/v1/voice/token",
            headers={"Origin": "https://trendibizz.com"},
            json={"key": tenant["public_key"],
                  "session_id": "voice-check-" + uuid.uuid4().hex},
        )
    print("Public voice token HTTP:", response.status_code)
    assert response.status_code == 200, "FAIL public voice token rejected"
    data = response.json()
    assert data["url"].startswith("wss://api.x.ai/v1/realtime"), "FAIL wrong voice provider"
    token = data["token"]
    protocol = token if token.startswith("xai-client-secret.") else "xai-client-secret." + token
    async with asyncio.timeout(60):
        async with websockets.connect(data["url"], subprotocols=[protocol], open_timeout=15) as websocket:
            await websocket.send(json.dumps({"type": "session.update", "session": data["session"]}))
            for _ in range(100):
                event = json.loads(await websocket.recv())
                assert event.get("type") != "error", "FAIL xAI rejected voice session or audio"
                if event.get("type") == "session.updated":
                    print("PASS Grok voice session accepted; voice:", data["session"]["voice"])
                    await websocket.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {"type": "message", "role": "user", "content": [{
                            "type": "input_text", "text": "Briefly describe what an office concierge does."
                        }]},
                    }))
                    await websocket.send(json.dumps({"type": "response.create"}))
                if event.get("type") in ("response.output_audio.delta", "response.audio.delta") and event.get("delta"):
                    print("PASS Grok generated audio output")
                    return
    raise AssertionError("FAIL no Grok audio output")


asyncio.run(main())
