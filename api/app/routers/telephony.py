"""Telephony routes: SMS webhooks, Grok Voice sessions/tools/recordings, Twilio PSTN relay,
live-call supervision/takeover, call insights, missed-call recovery, and phone setup.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qs
from xml.sax.saxutils import escape as xml_escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel, Field

from .. import (
    asterisk_ami, call_control, call_insights, casetimeline, channel_authorization,
    chat as chat_engine, convo, db, device_sms, enquiries, events, live_calls,
    managed_phone, missed_calls, outbox, owner_auth, phone_relay, sms, supervision,
    tenants, voice, voice_records,
)
from ..contact import normalize_phone
from ..security import require_admin

log = logging.getLogger("concierge")
router = APIRouter()
admin = [Depends(require_admin)]


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


def _twiml(text: str) -> Response:
    body = '<?xml version="1.0" encoding="UTF-8"?><Response>'
    if text:
        body += f"<Message>{xml_escape(text[:1500])}</Message>"
    body += "</Response>"
    return Response(content=body, media_type="application/xml")


@router.post("/api/v1/sms/{public_key}")
async def sms_inbound(public_key: str, request: Request):
    """Twilio inbound-SMS webhook: a visitor texts the client's number and the AI replies."""
    m = _main()
    settings = m.settings
    tenant = await tenants.get_by_key(public_key)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown key")
    if sms.provider() != "twilio" or not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="SMS is not configured")

    raw = (await request.body()).decode("utf-8", errors="replace")
    params = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
    url = settings.public_base_url.rstrip("/") + request.url.path
    if not sms.validate_signature(settings.twilio_auth_token, url, params, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="Invalid signature")

    if not tenant.get("sms_enabled"):
        raise HTTPException(status_code=403, detail="SMS is not enabled for this business")
    if not await channel_authorization.is_authorized(tenant["id"], "sms_read"):
        raise HTTPException(status_code=403, detail="Business has not authorized inbound SMS")
    sender = normalize_phone(params.get("From", ""), casetimeline.tenant_country_code(tenant))
    body = (params.get("Body") or "").strip()
    if not sender or not body:
        return _twiml("")
    # Twilio sends its own opt-out confirmation, so STOP gets no reply of ours here.
    reply = await m._sms_reply(tenant, sender, body, confirm_stop=False)
    is_compliance = body.upper() in (m.STOP_WORDS | m.START_WORDS | {"HELP"})
    if reply and not is_compliance and not await channel_authorization.is_authorized(tenant["id"], "sms_send"):
        return _twiml("")
    return _twiml(reply)


@router.post("/api/v1/sms/status/{outbox_id}")
async def sms_status(outbox_id: int, request: Request):
    """Existing Twilio transport only; signed callbacks never trigger another SMS."""
    settings = _main().settings
    if sms.provider() != "twilio" or not settings.twilio_auth_token:
        raise HTTPException(503, "SMS delivery callbacks disabled")
    params = await _phone_webhook_form(request)
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    if not sms.validate_signature(settings.twilio_auth_token, url, params,
                                  request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "Invalid signature")
    if params.get("AccountSid") != settings.twilio_account_sid:
        raise HTTPException(403, "Invalid account")
    from .. import sms_delivery
    if not await sms_delivery.twilio_receipt(outbox_id, params):
        raise HTTPException(400, "Unmatched or invalid SMS receipt")
    return {"ok": True}


@router.post("/api/v1/smsgate/{public_key}")
async def smsgate_inbound(public_key: str, request: Request):
    """Webhook for the self-hosted Android SMS gateway (event sms:received). The reply is sent as a
    new text, because the gateway has no reply-in-response mechanism like TwiML."""
    m = _main()
    settings = m.settings
    tenant = await tenants.get_by_key(public_key)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown key")
    if sms.provider() != "smsgate" or not settings.smsgate_signing_key:
        raise HTTPException(status_code=503, detail="SMS gateway is not configured")

    raw = await request.body()
    if not sms.validate_smsgate_signature(
        settings.smsgate_signing_key, raw,
        request.headers.get("X-Timestamp", ""), request.headers.get("X-Signature", ""),
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        envelope = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(envelope, dict):
        return {"ok": True}
    event = envelope.get("event")
    payload = envelope.get("payload") or {}
    if event in ("sms:sent", "sms:delivered", "sms:failed"):
        from .. import sms_delivery
        await sms_delivery.smsgate_receipt(tenant["id"], event, payload)
        return {"ok": True}
    if event != "sms:received":
        return {"ok": True}  # pings and other events are acknowledged and ignored

    if not tenant.get("sms_enabled") or tenant.get("sms_transport") == "device":
        raise HTTPException(status_code=403, detail="SMS gateway is not enabled for this business")
    if not await channel_authorization.is_authorized(tenant["id"], "sms_read"):
        raise HTTPException(status_code=403, detail="Business has not authorized inbound SMS")
    sender = normalize_phone(payload.get("sender") or payload.get("phoneNumber") or "", casetimeline.tenant_country_code(tenant))
    body = (payload.get("message") or "").strip()
    if not sender or not body:
        return {"ok": True}

    reply = await m._sms_reply(tenant, sender, body, confirm_stop=True)
    is_compliance = body.upper() in (m.STOP_WORDS | m.START_WORDS | {"HELP"})
    if reply and (is_compliance or await channel_authorization.is_authorized(tenant["id"], "sms_send")):
        msg_id = str(payload.get("messageId") or payload.get("id") or "")
        req_key = f"smsgate-inbound:{msg_id}" if msg_id else None
        events.spawn(_send_reply(tenant, sender, reply, request_key=req_key))
    return {"ok": True}


async def _send_reply(tenant: dict, to: str, text: str, *, request_key: str | None = None) -> None:
    try:
        await sms.send_sms(to, text[:1500], tenant.get("sms_from"), tenant=tenant, request_key=request_key)
    except Exception:
        log.exception("sms reply failed for %s", tenant["slug"])


async def _sms_reply(tenant: dict, sender: str, body: str, confirm_stop: bool) -> str:
    """Shared inbound-text logic for every provider. Returns the reply text, or "" for no reply."""
    m = _main()
    command = body.upper()
    if command in m.STOP_WORDS:
        await outbox.opt_out(tenant["id"], sender)
        return f"You're unsubscribed from {tenant['name']} messages. Reply START to resume." if confirm_stop else ""
    if command in m.START_WORDS:
        await outbox.opt_in(tenant["id"], sender)
        return f"You're subscribed to messages from {tenant['name']} again. Reply STOP to opt out."
    if command == "HELP":
        return f"{tenant['name']} AI assistant. Msg&data rates may apply. Reply STOP to opt out."
    if await outbox.is_opted_out(tenant["id"], sender):
        return ""

    session_id = "sms" + re.sub(r"\D", "", sender)
    if not m.sms_limiter.check(session_id):
        return ""
    conversation_id = await convo.get_or_create(tenant, session_id, "sms", None, None)
    await enquiries.capture(tenant, "sms", session_id, body,
                            conversation_id=conversation_id, phone=sender, consent_contact=True)
    try:
        result = await chat_engine.run_turn(tenant, session_id, "sms", body[:1000], sender_phone=sender)
    except Exception:
        log.exception("sms turn failed for %s", tenant["slug"])
        return "Sorry, I'm having trouble right now. The team will get back to you."
    if result.get("reason") == "human_takeover":
        # The owner is answering this person; keep their text in the thread the owner is reading.
        await convo.save_message(conversation_id, "user", body[:1000])
    return result["reply"]


class VoiceTokenRequest(BaseModel):
    key: str
    session_id: str
    recording_consent: bool = False


@router.post("/api/v1/voice/token")
async def voice_token(req: VoiceTokenRequest, request: Request):
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)
    try:
        result = await voice.mint_token(tenant)
        result["voice_session"] = await voice_records.start(tenant, session_id, record=req.recording_consent)
        return result
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Voice service unreachable")


class ToolRequest(BaseModel):
    key: str
    session_id: str
    args: dict = {}
    page_url: str | None = None
    utm: dict[str, str] = {}
    voice_session_id: uuid.UUID | None = None
    voice_session_token: str = Field(default="", max_length=200)


@router.post("/api/v1/tools/{name}")
async def tool_endpoint(name: str, req: ToolRequest, request: Request):
    """Called by the widget when Grok Voice invokes a function."""
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)
    conversation_id = await convo.get_or_create(tenant, session_id, "voice", req.page_url, req.utm)
    ctx = {
        "conversation_id": conversation_id,
        "channel": "voice",
        "page_url": req.page_url,
        "utm": convo.clean_utm(req.utm),
    }
    if req.voice_session_id:
        session = await voice_records.authenticate(req.voice_session_id, req.voice_session_token)
        if session["tenant_id"] != tenant["id"] or session["conversation_id"] != conversation_id:
            raise HTTPException(403, "Voice session does not belong to this conversation")
        ctx["voice_session"] = session
    return await m.run_tool(tenant, name, req.args, ctx)


class VoiceLogRequest(BaseModel):
    key: str
    session_id: str
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=4000)
    page_url: str | None = None
    utm: dict[str, str] = {}


@router.post("/api/v1/voice/log")
async def voice_log(req: VoiceLogRequest, request: Request):
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)
    conversation_id = await convo.get_or_create(tenant, session_id, "voice", req.page_url, req.utm)
    await convo.save_message(conversation_id, "user" if req.role == "user" else "assistant", req.text)
    return {"ok": True}


@router.post("/api/v1/voice/sessions/{session_id}/recording")
async def voice_recording_upload(session_id: uuid.UUID, request: Request):
    session = await voice_records.authenticate(session_id, request.headers.get("x-voice-session-token", ""))
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > voice_records.MAX_AUDIO:
            raise HTTPException(413, "Recording exceeds the size limit")
    return await voice_records.store_audio(session, bytes(body), request.headers.get("content-type", ""))


@router.post("/api/v1/voice/sessions/{session_id}/finish")
async def voice_session_finish(session_id: uuid.UUID, request: Request):
    session = await voice_records.authenticate(session_id, request.headers.get("x-voice-session-token", ""))
    tenant = await tenants.get_by_id(session["tenant_id"])
    if not tenant:
        raise HTTPException(404, "Business unavailable")
    return await voice_records.finish(session, tenant)


def private_audio_response(row, filename):
    return Response(bytes(row["audio"]), media_type=row["mime_type"], headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow, noarchive",
        "Content-Disposition": 'inline; filename="' + filename + '"',
    })


@router.get("/api/v1/voice/recordings/shared/{token}")
async def shared_voice_recording(token: str):
    row = await voice_records.shared_audio(token)
    return private_audio_response(row, "concierge-recording." + row["mime_type"].split("/")[1])


# -------------------------------------------------------- PSTN phone adapter (opt-in)
async def _phone_webhook_form(request: Request) -> dict[str, str]:
    # Twilio sends application/x-www-form-urlencoded, not multipart.
    if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raise HTTPException(status_code=415, detail="Invalid telephone webhook content type")
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(status_code=413, detail="Telephone webhook too large")
    try:
        items = parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
    except (UnicodeError, ValueError):
        raise HTTPException(status_code=400, detail="Malformed telephone webhook")
    if any(len(v) != 1 for v in items.values()):
        raise HTTPException(status_code=400, detail="Duplicate telephone webhook field")
    return {key: values[0] for key, values in items.items()}


@router.post("/api/v1/phone/twilio/inbound")
async def twilio_phone_inbound(request: Request):
    if not phone_relay.configured():
        raise HTTPException(status_code=503, detail="Telephone receptionist disabled")
    form = await _phone_webhook_form(request)
    uri = phone_relay.external_url("/api/v1/phone/twilio/inbound")
    if not phone_relay.signed(uri, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="Invalid telephone webhook signature")
    try:
        tenant = await phone_relay.register_inbound(form)
    except phone_relay.PhoneError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return Response(content=phone_relay.twiml(tenant), media_type="application/xml")


@router.post("/api/v1/phone/twilio/ended")
async def twilio_phone_ended(request: Request):
    if not phone_relay.configured():
        raise HTTPException(status_code=503, detail="Telephone receptionist disabled")
    form = await _phone_webhook_form(request)
    uri = phone_relay.external_url("/api/v1/phone/twilio/ended")
    if not phone_relay.signed(uri, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="Invalid telephone webhook signature")
    await phone_relay.finish(form.get("CallSid", ""), "completed")
    try:
        await missed_calls.evaluate_call_sid(form.get("CallSid", ""))
    except Exception:
        log.warning("Missed-call recovery needs reconciliation for a Twilio call")
    return Response(content='<Response><Hangup/></Response>', media_type="application/xml")


@router.post("/api/v1/phone/twilio/recording")
async def twilio_phone_recording_receipt(request: Request):
    if not phone_relay.configured() or not _main().settings.phone_recording_enabled:
        raise HTTPException(status_code=503, detail="Call recording disabled")
    form = await _phone_webhook_form(request)
    uri = phone_relay.external_url("/api/v1/phone/twilio/recording")
    if not phone_relay.signed(uri, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(status_code=403, detail="Invalid recording callback signature")
    try:
        await phone_relay.recording_callback(form)
    except phone_relay.PhoneError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@router.websocket("/api/v1/phone/relay")
async def twilio_phone_relay(websocket: WebSocket):
    await phone_relay.relay(websocket)


class PhoneNumberCreate(BaseModel):
    e164: str = Field(pattern=r"^\+[1-9]\d{6,14}$")


class PhoneNumberEnable(BaseModel):
    enabled: bool


@router.get("/admin/tenants/{slug}/phone-setup", dependencies=admin)
async def admin_phone_setup(slug: str):
    tenant = await _main()._require_tenant(slug)
    row = await db.pool().fetchrow(
        "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
        tenant["id"])
    return dict(row) if row else {"status": "not_requested"}


@router.get("/admin/tenants/{slug}/phone-numbers", dependencies=admin)
async def admin_phone_numbers(slug: str):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT e164, enabled, created_at FROM phone_numbers WHERE tenant_id=$1",
        tenant["id"],
    )
    return [dict(row) for row in rows]


@router.post("/admin/tenants/{slug}/phone-numbers", dependencies=admin, status_code=201)
async def admin_phone_number_create(slug: str, body: PhoneNumberCreate):
    tenant = await _main()._require_tenant(slug)
    row = await db.pool().fetchrow(
        "INSERT INTO phone_numbers (e164, tenant_id) VALUES ($1,$2) "
        "ON CONFLICT DO NOTHING RETURNING e164, enabled, created_at",
        body.e164, tenant["id"],
    )
    if row is None:
        raise HTTPException(status_code=409, detail="Number already registered")
    return dict(row)


@router.patch("/admin/tenants/{slug}/phone-numbers/{number}", dependencies=admin)
async def admin_phone_number_enable(slug: str, number: str, body: PhoneNumberEnable):
    tenant = await _main()._require_tenant(slug)
    row = await db.pool().fetchrow(
        "UPDATE phone_numbers SET enabled=$3 WHERE e164=$1 AND tenant_id=$2 "
        "RETURNING e164, enabled, created_at", number, tenant["id"], body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Number not found for this business")
    return dict(row)


@router.get("/admin/tenants/{slug}/phone-calls", dependencies=admin)
async def admin_phone_call_history(slug: str):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT call_sid, from_number, to_number, status, started_at, ended_at "
        "FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
        tenant["id"],
    )
    return [dict(row) for row in rows]


class LiveTakeover(BaseModel):
    reason: str = ""


class LiveSupervise(BaseModel):
    """How an owner wants to join a live call: hear it, coach it, or join it."""
    mode: Literal["listen", "whisper", "join"] = "listen"


@router.get("/owner/live-calls")
async def owner_live_calls(user: dict = Depends(owner_auth.current_user)):
    """Calls happening right now, with the conversation so far — the Switchboard, narrowed.

    Each call says which engine it is on and which controls are real for it (see live_calls.py).
    On the Asterisk line (`ast:`) the PBX owns the media, so take-over, listen-in and whisper are
    genuine audio actions; on Grok SIP calls (`sip:`) take-over stops the AI and alerts the owner
    to ring back, because that provider exposes no transfer or audio join.
    """
    return {"calls": await live_calls.active(user["tenant_id"]),
            "media_control": call_control.enabled()}


@router.get("/owner/live-calls/{call_sid}")
async def owner_live_call(call_sid: str, user: dict = Depends(owner_auth.current_user)):
    found = await live_calls.one(user["tenant_id"], call_sid)
    if not found:
        raise HTTPException(404, "Call not found")
    return found


@router.post("/owner/live-calls/{call_sid}/supervise")
async def owner_live_supervise(
    call_sid: str, body: LiveSupervise, user: dict = Depends(owner_auth.current_user)
):
    """Ring the owner's phone and join it to the live call: listen, whisper, or join.

    The media server does the work (Asterisk `ChanSpy` on the caller's channel through the same
    carrier trunk). Nothing is written to the caller's transcript — this is the owner listening.
    """
    owner_auth.require_role(user, "editor")
    tenant = await _main()._require_tenant(user["slug"])
    row = await db.pool().fetchrow(
        "SELECT * FROM phone_calls WHERE tenant_id = $1 AND call_sid = $2",
        user["tenant_id"], call_sid)
    if not row:
        raise HTTPException(404, "Call not found")
    call = dict(row)
    if not live_calls.is_live(call):
        raise HTTPException(409, "That call has already ended")
    by = user.get("email") or user.get("role") or "owner"
    try:
        result = await live_calls.supervise(tenant, call, body.mode, supervisor=str(by))
    except call_control.CallControlUnavailable as error:
        raise HTTPException(409, str(error))
    except asterisk_ami.AmiError as error:
        log.warning("supervise failed for %s: %s", call_sid, error)
        raise HTTPException(502, f"The switchboard did not answer: {error}")
    return {"ok": True, **result}


@router.post("/owner/live-calls/{call_sid}/supervise/stop")
async def owner_live_supervise_stop(
    call_sid: str, user: dict = Depends(owner_auth.current_user)
):
    """End every supervision leg on this call (the owner hanging up their own listening).

    The audit row closes with who stopped it; the caller and the assistant are untouched.
    """
    owner_auth.require_role(user, "editor")
    tenant = await _main()._require_tenant(user["slug"])
    row = await db.pool().fetchrow(
        "SELECT * FROM phone_calls WHERE tenant_id = $1 AND call_sid = $2",
        user["tenant_id"], call_sid)
    if not row:
        raise HTTPException(404, "Call not found")
    by = user.get("email") or user.get("role") or "owner"
    result = await live_calls.stop_supervision(tenant, call_sid, by=str(by))
    return {"ok": True, **result}


@router.get("/owner/supervision")
async def owner_supervision(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """The supervision audit trail: who listened to which call, in what mode, and for how long.

    Legs are closed against the PBX before they are read, so a supervisor who simply hung up
    their phone cannot leave a session showing as still listening.
    """
    await live_calls.reconcile_supervision(user["tenant_id"])
    return {"sessions": await supervision.recent(user["tenant_id"], limit),
            "media_control": call_control.enabled()}


@router.post("/owner/live-calls/{call_sid}/takeover")
async def owner_live_takeover(
    call_sid: str, body: LiveTakeover, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "editor")
    tenant = await _main()._require_tenant(user["slug"])
    row = await db.pool().fetchrow(
        "SELECT * FROM phone_calls WHERE tenant_id = $1 AND call_sid = $2",
        user["tenant_id"], call_sid)
    if not row:
        raise HTTPException(404, "Call not found")
    call = dict(row)
    if not live_calls.is_live(call):
        raise HTTPException(409, "That call has already ended; use Contacts to follow it up")
    by = user.get("email") or user.get("role") or "owner"
    try:
        result = await live_calls.take_over(tenant, call, by=str(by))
    except (call_control.CallControlUnavailable, asterisk_ami.AmiError) as error:
        raise HTTPException(502, f"The switchboard did not answer: {error}")
    return {"ok": True, **result}


@router.get("/owner/call-insights")
async def owner_call_insights(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """What happened on recent calls: summary, outcome, how the caller felt, the next step."""
    rows = await call_insights.recent(user["tenant_id"], limit)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    return {"insights": rows, "counts_by_outcome": counts, "outcomes": list(call_insights.OUTCOMES)}


@router.get("/owner/phone-setup")
async def owner_phone_setup(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
        user["tenant_id"])
    return dict(row) if row else {"status": "not_requested"}


@router.put("/owner/phone-setup")
async def owner_save_phone_setup(body: managed_phone.PhoneSetup, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await managed_phone.save_setup(user["tenant_id"], body)


@router.get("/owner/phone-numbers")
async def owner_phone_numbers(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT e164,enabled,created_at FROM phone_numbers WHERE tenant_id=$1",
        user["tenant_id"],
    )
    return [dict(row) for row in rows]


@router.get("/owner/sms-phone")
async def owner_sms_phone(user: dict = Depends(owner_auth.current_user)):
    device = await db.pool().fetchrow(
        "SELECT from_number,last_seen,verified_at,"
        "(inbound_verified_at IS NOT NULL OR EXISTS(SELECT 1 FROM device_sms_inbound i WHERE i.device_id=sms_devices.id)) AS receive_verified "
        "FROM sms_devices WHERE tenant_id=$1 AND enabled", user["tenant_id"])
    jobs = await db.pool().fetch(
        "SELECT recipient,body,status,created_at FROM device_sms_jobs "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 20", user["tenant_id"])
    online = bool(device and device["last_seen"] and
                  (datetime.now(timezone.utc) - device["last_seen"]).total_seconds() < 300)
    return {"paired": bool(device), "online": online,
            "number": device["from_number"] if device else "",
            "send_verified": bool(device and device["verified_at"]),
            "receive_verified": bool(device and device["receive_verified"]),
            "messages": [dict(row) for row in jobs]}


class PhoneSmsTest(BaseModel):
    model_config = {"extra": "forbid"}
    acknowledgement: Literal[True]
    request_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


class MissedCallTextback(BaseModel):
    enabled: bool


@router.get("/owner/missed-calls")
async def owner_missed_calls(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """What we did about calls nobody answered, so the owner is never guessing."""
    tenant = await _main()._require_tenant(user["slug"])
    rows = await missed_calls.recent(user["tenant_id"], max(1, min(limit, 100)))
    return {
        "enabled": bool(tenant.get("missed_call_textback")),
        "template": tenant.get("missed_call_template") or "",
        "count_30d": await db.pool().fetchval(
            "SELECT count(*) FROM missed_call_recoveries WHERE tenant_id=$1 AND status='queued' "
            "AND created_at>now()-interval '30 days'", user["tenant_id"]),
        "recoveries": rows,
    }


@router.put("/owner/missed-calls/textback")
async def owner_set_missed_textback(
    body: MissedCallTextback, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    await db.pool().execute(
        "UPDATE tenants SET missed_call_textback=$2 WHERE id=$1", user["tenant_id"], body.enabled)
    return {"enabled": body.enabled}


@router.post("/owner/sms-phone/test", status_code=202)
async def owner_sms_phone_test(body: PhoneSmsTest, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    tenant = await _main()._require_tenant(user["slug"])
    previous = await db.pool().fetchval(
        "SELECT id FROM device_sms_jobs WHERE tenant_id=$1 AND request_key LIKE 'phone-test:%' "
        "AND created_at>now()-interval '1 minute' LIMIT 1", user["tenant_id"])
    if previous:
        return {"status": "awaiting_phone_result"}
    try:
        await device_sms.enqueue(
            tenant, tenant.get("sms_from") or "",
            "Trendi Concierge SMS connection test. No reply needed.", "phone-test:" + body.request_id)
    except device_sms.AwaitingReceipt:
        return {"status": "awaiting_phone_result"}
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except device_sms.ReconciliationRequired:
        raise HTTPException(409, "Previous phone result needs review before another test") from None
    return {"status": "sent"}


@router.get("/owner/phone-calls")
async def owner_phone_calls(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT call_sid,from_number,to_number,status,started_at,ended_at, "
        "recording_consent,recording_status "
        "FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
        user["tenant_id"],
    )
    return [dict(row) for row in rows]


@router.get("/owner/phone-calls/{call_id}/transcript")
async def owner_phone_transcript(call_id: str, user: dict = Depends(owner_auth.current_user)):
    found = await db.pool().fetchval('SELECT 1 FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2', user['tenant_id'], call_id)
    if not found:
        raise HTTPException(404, 'Call not found')
    rows = await db.pool().fetch(
        "SELECT m.role,m.content,m.created_at FROM phone_calls p "
        "JOIN conversations c ON c.tenant_id=p.tenant_id AND c.session_id=p.call_sid AND c.channel='phone' "
        "JOIN messages m ON m.conversation_id=c.id WHERE p.tenant_id=$1 AND p.call_sid=$2 "
        "AND m.role IN ('user','assistant') ORDER BY m.id LIMIT 200", user['tenant_id'], call_id)
    return [dict(row) for row in rows]
