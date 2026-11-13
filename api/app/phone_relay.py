"""Opt-in Twilio Conversation Relay adapter for inbound phone calls.

Twilio handles speech-to-text and text-to-speech. Concierge handles the text dialogue.
This module does not purchase telephone numbers, make outbound calls or record audio.
A real number and signed production webhook/WSS tests are required before rollout.
"""
import asyncio
import logging
import httpx
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

from fastapi import WebSocket, WebSocketDisconnect

from . import channel_authorization, chat, convo, db, enquiries, sms, tenants
from .config import get_settings

log = logging.getLogger("concierge.phone")

CALL_SID = re.compile(r"^CA[0-9a-fA-F]{32}$")
NUMBER = re.compile(r"^\+[1-9]\d{6,14}$")
MAX_TURNS = 20
MAX_SECONDS = 600
RECORDING_CONSENT = re.compile(
    r"^(?:yes[,]?[ ]+)?i consent to (?:this )?(?:call )?recording[.!]?$",
    re.IGNORECASE,
)
RECORDING_DECLINE = "not_granted"



class PhoneError(ValueError):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(
        s.phone_voice_provider == 'legacy_twilio_tts'
        and s.phone_receptionist_enabled and s.twilio_auth_token
        and s.public_base_url.startswith("https://")
    )


def external_url(path: str, websocket: bool = False) -> str:
    base = get_settings().public_base_url.rstrip("/")
    if not base.startswith("https://"):
        raise PhoneError("Public HTTPS URL required for telephone reception")
    return ("wss://" + base[len("https://"):] if websocket else base) + path


def signed(url: str, params: dict[str, str], signature: str) -> bool:
    secret = get_settings().twilio_auth_token
    if not secret or not signature:
        return False
    return sms.validate_signature(secret, url, params, signature)


def valid_websocket_signature(signature: str) -> bool:
    # Twilio's WSS signature may include a trailing slash depending on the edge.
    url = external_url("/api/v1/phone/relay", websocket=True)
    return signed(url, {}, signature) or signed(url + "/", {}, signature)


def twiml(tenant: dict) -> str:
    """Generate TwiML only for an explicitly enabled business."""
    ws = xml_escape(external_url("/api/v1/phone/relay", websocket=True), {'"': "&quot;"})
    action = xml_escape(external_url("/api/v1/phone/twilio/ended"), {'"': "&quot;"})
    greeting_text = (
        f"Hello, you've reached {tenant['name']}'s automated receptionist. "
        "This call may be transcribed to answer your enquiry. "
    )
    if tenant.get("_recording_offer"):
        greeting_text += (
            "Recording is optional. To record this call, say exactly "
            "'I consent to recording' as your first response. "
            "Otherwise, just tell me how I can help and this call will not be recorded."
        )
    else:
        greeting_text += "How can I help?"
    greeting = xml_escape(greeting_text, {'"': "&quot;"})
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Connect action="' + action + '" method="POST">'
        '<ConversationRelay url="' + ws + '" welcomeGreeting="' + greeting +
        '" echoPromptFiltering="true" language="en-US" />'
        '</Connect></Response>'
    )


async def register_inbound(params: dict[str, str]) -> dict:
    if not configured():
        raise PhoneError("Telephone reception disabled")
    call_sid = params.get("CallSid", "")
    to_number = params.get("To", "")
    from_number = params.get("From", "")
    if not CALL_SID.fullmatch(call_sid) or not NUMBER.fullmatch(to_number):
        raise PhoneError("Invalid call identifier or destination")
    row = await db.pool().fetchrow(
        """SELECT t.* FROM phone_numbers p
           JOIN tenants t ON t.id = p.tenant_id
           WHERE p.e164=$1 AND p.enabled AND t.phone_enabled""", to_number
    )
    if not row:
        raise PhoneError("This number has no enabled receptionist")
    tenant = dict(row)
    if not await channel_authorization.is_authorized(tenant["id"], "telephone"):
        raise PhoneError("Business has not authorized telephone reception")
    tenant["_recording_offer"] = bool(
        get_settings().phone_recording_enabled
        and await channel_authorization.is_authorized(tenant["id"], "call_recording")
        and get_settings().twilio_account_sid
        and get_settings().twilio_auth_token
    )
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", "phone:" + call_sid)
            previous = await conn.fetchrow(
                "SELECT tenant_id FROM phone_calls WHERE call_sid=$1", call_sid
            )
            if previous:
                if previous["tenant_id"] != tenant["id"]:
                    raise PhoneError("Call already registered for another business")
            await conn.execute("SELECT id FROM tenants WHERE id=$1 FOR UPDATE", tenant["id"])
            used = await conn.fetchval(
                "SELECT count(*) FROM phone_calls WHERE tenant_id=$1 "
                "AND started_at >= now() - interval '1 day'", tenant["id"]
            )
            if not previous and used >= tenant["phone_daily_limit"]:
                raise PhoneError("Daily telephone limit reached")
            await conn.execute(
                """INSERT INTO phone_calls (tenant_id, call_sid, from_number, to_number)
                   VALUES ($1,$2,$3,$4) ON CONFLICT(call_sid) DO NOTHING""",
                tenant["id"], call_sid, from_number[:40], to_number
            )
    conversation_id = await convo.get_or_create(tenant, call_sid, "phone", None, None)
    await enquiries.capture(tenant, "phone", call_sid, "Inbound telephone enquiry",
                            conversation_id=conversation_id,
                            phone=from_number if NUMBER.fullmatch(from_number) else "")
    return tenant


async def finish(call_sid: str, status: str) -> None:
    if not CALL_SID.fullmatch(call_sid):
        return
    await db.pool().execute(
        "UPDATE phone_calls SET status=$2, ended_at=COALESCE(ended_at,now()) "
        "WHERE call_sid=$1 AND (status <> 'completed' OR $2 = 'completed')",
        call_sid, status[:40]
    )


async def _record_setup(data: dict) -> dict | None:
    sid = data.get("callSid", "")
    session = data.get("sessionId", "")
    row = await db.pool().fetchrow(
        """SELECT p.*, t.slug AS tenant_slug FROM phone_calls p
           JOIN tenants t ON t.id=p.tenant_id
           WHERE p.call_sid=$1 AND t.phone_enabled""", sid
    )
    if not row or not session or not isinstance(session, str):
        return None
    if row["to_number"] != data.get("to"):
        return None
    # A call originating from a hidden caller ID may omit its 'from'.
    if row["from_number"] and row["from_number"] != data.get("from"):
        return None
    tenant = await tenants.get_by_id(row["tenant_id"])
    if not tenant:
        return None
    await db.pool().execute(
        "UPDATE phone_calls SET session_id=$2, status='in_progress' WHERE call_sid=$1",
        sid, session[:100],
    )
    tenant["_recording_offer"] = bool(
        get_settings().phone_recording_enabled
        and get_settings().twilio_account_sid
        and get_settings().twilio_auth_token
        and await channel_authorization.is_authorized(tenant["id"], "call_recording")
    )
    return tenant


async def begin_recording(call_sid: str, tenant: dict) -> bool:
    """Start provider recording ONLY after an explicit caller opt-in.

    Provider response must be successful and include a valid RecordingSid.
    Recording media stays at provider; this function stores only state/IDs.
    """
    cfg = get_settings()
    if (not CALL_SID.fullmatch(call_sid)
            or not cfg.phone_recording_enabled
            or not cfg.twilio_account_sid.startswith("AC")
            or len(cfg.twilio_account_sid) != 34
            or not cfg.twilio_auth_token
            or not await channel_authorization.is_authorized(tenant["id"], "call_recording")):
        return False
    row = await db.pool().fetchrow(
        """UPDATE phone_calls SET recording_consent='granted',consent_at=now(),
                  recording_status='requested'
           WHERE call_sid=$1 AND tenant_id=$2 AND status='in_progress'
             AND recording_consent='not_requested'
           RETURNING call_sid""",
        call_sid, tenant["id"],
    )
    if not row:
        return False
    url = (f"https://api.twilio.com/2010-04-01/Accounts/"
           f"{cfg.twilio_account_sid}/Calls/{call_sid}/Recordings.json")
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            response = await client.post(
                url,
                auth=(cfg.twilio_account_sid, cfg.twilio_auth_token),
                data={
                    "RecordingStatusCallback": external_url("/api/v1/phone/twilio/recording"),
                    "RecordingStatusCallbackEvent": "completed absent",
                    "RecordingChannels": "dual",
                },
            )
        if response.status_code not in (200, 201):
            raise PhoneError("Recording provider rejected request")
        payload = response.json()
        recording_sid = payload.get("sid", "")
        if not re.fullmatch(r"RE[0-9a-fA-F]{32}", recording_sid):
            raise PhoneError("Invalid recording receipt")
        await db.pool().execute(
            """UPDATE phone_calls
               SET recording_sid=COALESCE(recording_sid,$3),
                   recording_status=CASE
                     WHEN recording_status IN ('completed','absent','failed')
                     THEN recording_status ELSE 'in_progress' END
               WHERE call_sid=$1 AND tenant_id=$2
                 AND recording_consent='granted'
                 AND (recording_sid IS NULL OR recording_sid=$3)""",
            call_sid, tenant["id"], recording_sid,
        )
        return True
    except (httpx.HTTPError, ValueError, PhoneError):
        log.warning("Recording start not confirmed for consented call")
        await db.pool().execute(
            """UPDATE phone_calls SET recording_status='failed'
               WHERE call_sid=$1 AND tenant_id=$2""", call_sid, tenant["id"],
        )
        return False


async def recording_callback(params: dict[str, str]) -> None:
    """Signed Twilio callback. Never assume media is safely retained on receipt."""
    sid = params.get("CallSid", "")
    rec = params.get("RecordingSid", "")
    status = params.get("RecordingStatus", "")
    if not CALL_SID.fullmatch(sid) or not re.fullmatch(r"RE[0-9a-fA-F]{32}", rec):
        raise PhoneError("Invalid recording identifiers")
    if status not in {"in-progress", "completed", "absent", "failed"}:
        raise PhoneError("Invalid recording status")
    await db.pool().execute(
        """UPDATE phone_calls
           SET recording_sid=COALESCE(recording_sid,$2),
               recording_status=CASE
                 WHEN recording_status IN ('completed','absent','failed')
                 THEN recording_status ELSE $3 END
           WHERE call_sid=$1 AND recording_consent='granted'
             AND recording_status IN ('requested','in_progress','completed','absent','failed')
             AND (recording_sid=$2 OR recording_sid IS NULL)""",
        sid, rec, status,
    )


async def relay(websocket: WebSocket) -> None:
    """Authenticated, bounded WebSocket session. Speech comes from Twilio, not the browser."""
    if not configured() or not valid_websocket_signature(
        websocket.headers.get("x-twilio-signature", "")
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    tenant = None
    session = None
    turns = 0
    started = asyncio.get_running_loop().time()
    current: asyncio.Task | None = None
    awaiting_recording_consent = False

    async def respond(prompt: str):
        try:
            conversation_id = await convo.get_or_create(tenant, session, "phone", None, None)
            # The streaming socket does not carry the caller's number, but the call record does.
            # Without this the mid-call enquiries attach to an anonymous case.
            stored = await db.pool().fetchrow(
                "SELECT from_number FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2",
                tenant["id"], session)
            caller = (stored["from_number"] if stored else "") or ""
            await enquiries.capture(tenant, "phone", session, prompt,
                                    conversation_id=conversation_id,
                                    phone=caller if NUMBER.fullmatch(caller) else "")
            result = await chat.run_turn(
                tenant, session, "phone", prompt, sender_phone=None
            )
            reply = (result.get("reply") or "").strip()
            if not reply:
                reply = "I could not find that answer. The team can follow up with you."
            await websocket.send_json({"type": "text", "token": reply[:1200], "last": True})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Phone response failed")
            try:
                await websocket.send_json({
                    "type": "text",
                    "token": "Sorry, I'm having trouble right now. Please contact the team through our website.",
                    "last": True
                })
            except Exception:
                pass

    try:
        while True:
            if asyncio.get_running_loop().time() - started >= MAX_SECONDS:
                await websocket.send_json({"type": "end", "handoffData": '{"reason":"time_limit"}'})
                break
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
            except asyncio.TimeoutError:
                continue
            kind = data.get("type")
            if tenant is None:
                if kind != "setup":
                    await websocket.close(code=1008)
                    break
                tenant = await _record_setup(data)
                if not tenant:
                    await websocket.close(code=1008)
                    break
                session = str(data["callSid"])
                awaiting_recording_consent = bool(tenant.get("_recording_offer"))
                continue
            if kind == "prompt" and data.get("last") is True:
                prompt = str(data.get("voicePrompt") or "").strip()[:1000]
                if not prompt:
                    continue
                if awaiting_recording_consent:
                    awaiting_recording_consent = False
                    if RECORDING_CONSENT.fullmatch(prompt):
                        succeeded = await begin_recording(session, tenant)
                        await websocket.send_json({
                            "type": "text",
                            "token": (
                                "Thank you. Recording has started. How can I help?"
                                if succeeded else
                                "Recording could not be started, so this call will continue without recording. How can I help?"
                            ),
                            "last": True,
                        })
                        continue
                    # An ordinary first enquiry is not consent. This call will
                    # continue without recording. No implicit YES parsing.
                    await db.pool().execute(
                        """UPDATE phone_calls SET recording_consent=$2
                           WHERE call_sid=$1 AND recording_consent='not_requested'""",
                        session, RECORDING_DECLINE,
                    )
                turns += 1
                if turns > MAX_TURNS:
                    await websocket.send_json({
                        "type": "text", "token": "I have reached my call limit. Please contact the team directly.",
                        "last": True
                    })
                    await websocket.send_json({"type": "end", "handoffData": '{"reason":"turn_limit"}'})
                    break
                if current and not current.done():
                    current.cancel()
                    try:
                        await current
                    except asyncio.CancelledError:
                        pass
                current = asyncio.create_task(respond(prompt))
            elif kind == "interrupt":
                if current and not current.done():
                    current.cancel()
                    try:
                        await current
                    except asyncio.CancelledError:
                        pass
            elif kind == "error":
                log.warning("Twilio relay error for call (code only): %s", data.get("code"))
            # setup/info/dtmf/unknown events are ignored; no externally-triggered actions.
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("Phone relay failed")
    finally:
        if current and not current.done():
            current.cancel()
            try:
                await current
            except (asyncio.CancelledError, Exception):
                pass
        if session:
            await finish(session, "relay_ended")
