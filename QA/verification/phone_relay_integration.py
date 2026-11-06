"""Simulated Twilio Conversation Relay integration, with disposable database.

No Twilio credentials, paid calls or real AI requests are used.
"""
import base64
import hashlib
import hmac
import os
from unittest.mock import patch

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "ADMIN_TOKEN": "phone-test-admin",
    "OUTBOX_ENABLED": "false",
    "PHONE_RECEPTIONIST_ENABLED": "true",
    "PUBLIC_BASE_URL": "https://chat.example.test",
    "TWILIO_AUTH_TOKEN": "not-a-real-token",
})

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402
from app import chat, db, phone_relay  # noqa: E402
from app.main import app  # noqa: E402

n = 0
H = {"X-Admin-Token": "phone-test-admin"}
CALL = "CA" + "a" * 32
FROM = "+64215550123"
TO = "+6495550123"


def check(label, condition):
    global n
    assert condition, label
    n += 1
    print("PASS", label)


def sign(url, params=None):
    params = params or {}
    body = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(
        hmac.new(b"not-a-real-token", body.encode(), hashlib.sha1).digest()
    ).decode()


with TestClient(app) as client:
    run = client.portal.call
    p = db.pool()

    async def seed():
        a = await p.fetchval(
            "INSERT INTO tenants(slug,name,public_key) VALUES "
            "('alpha','Alpha Plumbing','pk_a') RETURNING id")
        b = await p.fetchval(
            "INSERT INTO tenants(slug,name,public_key) VALUES "
            "('beta','Beta Repairs','pk_b') RETURNING id")
        return a,b

    alpha, beta = run(seed)
    check("new tenant telephone off", run(lambda: p.fetchval(
        "SELECT phone_enabled FROM tenants WHERE id=$1", alpha)) is False)
    check("new tenant browser voice off", run(lambda: p.fetchval(
        "SELECT voice_enabled FROM tenants WHERE id=$1", alpha)) is False)

    create_url = "/admin/tenants/alpha/phone-numbers"
    r = client.post(create_url, json={"e164": TO})
    check("provisioning requires admin token", r.status_code == 401)
    r = client.post(create_url, headers=H, json={"e164": TO})
    check("number registered inactive", r.status_code == 201 and r.json()["enabled"] is False)
    r = client.post("/admin/tenants/beta/phone-numbers", headers=H, json={"e164": TO})
    check("number cannot belong to two tenants", r.status_code == 409)
    r = client.post(create_url, headers=H, json={"e164": "abc"})
    check("invalid phone number rejected", r.status_code == 422)

    params = {"CallSid": CALL, "From": FROM, "To": TO}
    hook = "/api/v1/phone/twilio/inbound"
    signed_headers = {"X-Twilio-Signature": sign("https://chat.example.test" + hook, params)}
    r = client.post(hook, data=params, headers={"X-Twilio-Signature": "bad"})
    check("unsigned voice webhook rejected", r.status_code == 403)
    r = client.post(hook, data=params, headers=signed_headers)
    check("inactive number rejects even signed webhook", r.status_code == 403)
    r = client.patch("/admin/tenants/alpha", headers=H, json={"phone_enabled": True})
    check("operator can opt in one business", r.status_code == 200 and r.json()["phone_enabled"] is True)
    r = client.patch(create_url + "/" + TO, headers=H, json={"enabled": True})
    check("number activation requires explicit action", r.status_code == 200 and r.json()["enabled"] is True)
    r = client.post(hook, data=params, headers=signed_headers)
    check("valid signed webhook returns TwiML", r.status_code == 200 and "<ConversationRelay" in r.text)
    check("TwiML has secure WebSocket and end callback",
          "wss://chat.example.test/api/v1/phone/relay" in r.text
          and "https://chat.example.test/api/v1/phone/twilio/ended" in r.text)
    check("greeting discloses automated assistant",
          "automated receptionist" in r.text and "transcribed" in r.text)
    r = client.post(hook, data=params, headers=signed_headers)
    check("retrying same call is safe", r.status_code == 200)
    check("one call row, no duplicates", run(lambda: p.fetchval(
        "SELECT count(*) FROM phone_calls WHERE tenant_id=$1", alpha)) == 1)
    r = client.get("/admin/tenants/beta/phone-calls", headers=H)
    check("other business cannot list alpha call", r.status_code == 200 and r.json() == [])

    async def fake_run_turn(tenant, session_id, channel, text, **kwargs):
        return {"reply": "Thanks, I can help with your enquiry."}
    websocket_url = "wss://chat.example.test/api/v1/phone/relay"
    ws_headers = {"X-Twilio-Signature": sign(websocket_url)}
    with patch.object(chat, "run_turn", new=fake_run_turn):
        try:
            with client.websocket_connect("/api/v1/phone/relay", headers={
                "X-Twilio-Signature": "forged"
            }) as ws:
                ws.receive_json()
        except WebSocketDisconnect as exc:
            check("unsigned websocket rejected", exc.code == 1008)

        with client.websocket_connect("/api/v1/phone/relay", headers=ws_headers) as ws:
            ws.send_json({
                "type": "setup", "callSid": CALL, "sessionId": "VX" + "f" * 32,
                "from": FROM, "to": TO, "connectionType": "initial"
            })
            ws.send_json({"type": "prompt", "voicePrompt": "What hours are you open?", "last": True})
            result = ws.receive_json()
            check("real-time prompt receives speech text", result == {
                "type": "text", "token": "Thanks, I can help with your enquiry.", "last": True
            })
            ws.send_json({"type": "info", "test": "ignored"})

    check("call remains registered while termination callback pending", run(lambda: p.fetchval(
        "SELECT status FROM phone_calls WHERE call_sid=$1", CALL)) in ("in_progress", "relay_ended"))

    finished = "/api/v1/phone/twilio/ended"
    end_form = {"CallSid": CALL, "SessionStatus": "ended"}
    r = client.post(finished, data=end_form, headers={
        "X-Twilio-Signature": sign("https://chat.example.test" + finished, end_form)
    })
    check("signed completion accepted", r.status_code == 200 and "<Hangup" in r.text)
    check("call complete in history", run(lambda: p.fetchval(
        "SELECT status FROM phone_calls WHERE call_sid=$1", CALL)) == "completed")

    run(lambda: phone_relay.finish(CALL, "relay_ended"))
    check("late socket cleanup cannot erase completed status", run(lambda: p.fetchval(
        "SELECT status FROM phone_calls WHERE call_sid=$1", CALL)) == "completed")

print(f"{n}/{n} simulated phone checks passed")
