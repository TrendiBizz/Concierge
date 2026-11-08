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
    "PHONE_VOICE_PROVIDER": "legacy_twilio_tts",  # historical adapter only; production uses native Grok SIP
    "PUBLIC_BASE_URL": "https://chat.example.test",
    "TWILIO_AUTH_TOKEN": "not-a-real-token",
    "TWILIO_ACCOUNT_SID": "AC" + "a" * 32,
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
    check("signed phone call blocked without owner authorization", r.status_code == 403)
    async def authorize_telephone():
        uid = await p.fetchval(
            "INSERT INTO tenant_users(tenant_id,email,role,password_hash) "
            "VALUES($1,'owner@alpha.invalid','owner','test') RETURNING id", alpha
        )
        await p.execute(
            "INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) "
            "VALUES($1,'telephone',true,$2)", alpha, uid,
        )
    run(authorize_telephone)
    r = client.post(hook, data=params, headers=signed_headers)
    check("valid signed and authorized webhook returns TwiML",
          r.status_code == 200 and "<ConversationRelay" in r.text)
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

    # Recording is explicitly off by default even when phone service works.
    first = run(lambda: p.fetchrow(
        "SELECT recording_consent,recording_sid FROM phone_calls WHERE call_sid=$1", CALL
    ))
    check("ordinary enquiry never started recording",
          first["recording_sid"] is None and first["recording_consent"] == "not_requested")

    async def authorize_recording():
        uid = await p.fetchval(
            "SELECT id FROM tenant_users WHERE tenant_id=$1 LIMIT 1", alpha
        )
        await p.execute(
            "INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) "
            "VALUES($1,'call_recording',true,$2)", alpha, uid
        )
    run(authorize_recording)

    # No provider call: mock the Twilio REST response while using the real DB.
    from app.main import settings as api_settings
    from types import SimpleNamespace
    class FakeRecordingClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def post(self, url, **kwargs):
            assert url.endswith("/Recordings.json")
            assert kwargs["data"]["RecordingStatusCallback"].endswith("/api/v1/phone/twilio/recording")
            return SimpleNamespace(status_code=201, json=lambda: {"sid": "RE" + "b" * 32})
    api_settings.phone_recording_enabled = True
    RECORD_CALL = "CA" + "b" * 32
    record_form = {"CallSid": RECORD_CALL, "From": FROM, "To": TO}
    rr = client.post(hook, data=record_form, headers={
        "X-Twilio-Signature": sign("https://chat.example.test" + hook, record_form)
    })
    check("recording is offered only for authorized business",
          rr.status_code == 200 and "I consent to recording" in rr.text)
    with patch.object(phone_relay.httpx, "AsyncClient", return_value=FakeRecordingClient()):
        with client.websocket_connect("/api/v1/phone/relay", headers=ws_headers) as ws:
            ws.send_json({
                "type": "setup", "callSid": RECORD_CALL, "sessionId": "VX" + "a"*32,
                "from": FROM, "to": TO, "connectionType": "initial"
            })
            ws.send_json({"type": "prompt", "voicePrompt": "I consent to recording", "last": True})
            message = ws.receive_json()
            check("explicit caller consent is required before recording starts",
                  message["last"] and "Recording has started" in message["token"])
    state = run(lambda: p.fetchrow(
        "SELECT recording_consent,recording_sid,recording_status FROM phone_calls WHERE call_sid=$1",
        RECORD_CALL
    ))
    check("recording metadata persists without storing audio",
          state["recording_consent"] == "granted"
          and state["recording_sid"] == "RE" + "b" * 32
          and state["recording_status"] == "in_progress")
    callback = "/api/v1/phone/twilio/recording"
    values = {"CallSid": RECORD_CALL, "RecordingSid": "RE"+"b"*32, "RecordingStatus": "completed"}
    check("forged recording status rejected",
          client.post(callback, data=values, headers={"X-Twilio-Signature": "forged"}).status_code == 403)
    authenticated = client.post(callback, data=values, headers={
        "X-Twilio-Signature": sign("https://chat.example.test"+callback, values)
    })
    check("signed recording receipt updates matching call only",
          authenticated.status_code == 200 and
          run(lambda: p.fetchval(
              "SELECT recording_status FROM phone_calls WHERE call_sid=$1", RECORD_CALL
          )) == "completed")
    api_settings.phone_recording_enabled = False

print(f"{n}/{n} simulated phone checks passed")
