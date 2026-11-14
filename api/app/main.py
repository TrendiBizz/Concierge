import asyncio
import base64
import hmac
import html
import time
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, quote_plus, urlsplit
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import (
    automation, campaigns, chat as chat_engine, convo, db, email_drafts, enquiries, events, ical, ingest, llm, outbox, sales, scoring, sla,
    phone_relay, owner_auth, owner_onboarding, owner_knowledge, channel_authorization, social_bridge, sms, tasks, tenants, tenant_pause, unsub, voice, cloudflare_inbound, device_sms, phone_sip, managed_phone, voice_records, inbound_policy, voice_internal, products, reply_address, designs, media_studio,
)
from . import cloudflare_auth, inbound_readiness, mobile_connections, quotations, calendar_connection, email_secretary, hermes_ops, brand_from_site
from . import suppressions
from . import owner_invites
from . import install_requests
from . import privacy
from . import platform_billing
from . import invoices
from . import guides
from . import quote_profiles
from . import portability
from . import channel_health, flood_guard, mailer
from . import asterisk_ami, call_control, call_insights, casetimeline, hermes_orchestrator, live_calls, missed_calls, provider_readiness, quote_payments, revenue, supervision
from .booking import DAYS
from .config import get_settings
from .contact import normalize_phone
from .security import RateLimiter, require_admin
from .tools import run_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("concierge")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

settings = get_settings()
ip_limiter = RateLimiter(settings.chat_rate_per_minute_ip, 60)
session_limiter = RateLimiter(settings.chat_rate_per_day_session, 86_400)
sms_limiter = RateLimiter(12, 3600)  # AI replies per contact per hour (was 30): stops bot-to-bot SMS loops

LEAD_STATUSES = ("new", "contacted", "booked", "won", "lost")
APPT_STATUSES = ("booked", "completed", "cancelled", "no_show")
STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
START_WORDS = {"START", "UNSTOP"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init()
    await tenants.ensure_report_tokens()
    await tenants.ensure_calendar_tokens()
    stop = asyncio.Event()
    async def maintain_voice_records():
        while not stop.is_set():
            try:
                await voice_records.purge_expired()
            except Exception:
                log.warning("Voice recording retention cleanup will retry")
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                pass
    voice_retention_worker = asyncio.create_task(maintain_voice_records())
    worker = asyncio.create_task(outbox.run_forever(stop)) if settings.outbox_enabled else None
    sla_worker = asyncio.create_task(sla.run_forever(stop)) if settings.outbox_enabled else None
    digest_worker = asyncio.create_task(sales.run_forever(stop)) if settings.outbox_enabled else None
    missed_worker = asyncio.create_task(missed_calls.run_forever(stop)) if settings.outbox_enabled else None
    insights_worker = asyncio.create_task(call_insights.run_forever(stop)) if settings.outbox_enabled else None
    twenty_worker = asyncio.create_task(events.run_twenty_forever(stop)) if (
        settings.twenty_bridge_url and settings.twenty_bridge_tenant_slug) else None
    email_worker = asyncio.create_task(email_secretary.run_forever(stop))
    calendar_worker = asyncio.create_task(calendar_connection.run_forever(stop))
    yield
    stop.set()
    await calendar_worker
    await email_worker
    await voice_retention_worker
    if worker:
        await worker
    if sla_worker:
        await sla_worker
    if digest_worker:
        await digest_worker
    if twenty_worker:
        await twenty_worker
    await db.close()


app = FastAPI(title="Website AI Concierge", lifespan=lifespan)

app.include_router(voice_internal.router)
app.include_router(device_sms.router)
app.include_router(phone_sip.router)
app.include_router(managed_phone.router)
app.include_router(mobile_connections.router)
app.include_router(quotations.router)
app.include_router(quotations.public_router)
app.include_router(products.router)
app.include_router(guides.router)
app.include_router(quote_profiles.router)
app.include_router(invoices.router)
app.include_router(invoices.public_router)
app.include_router(privacy.router)
app.include_router(privacy.public_router)
app.include_router(platform_billing.router)
app.include_router(platform_billing.public_router)
app.include_router(designs.router)
app.include_router(designs.public_router)
app.include_router(designs.page_router)
app.include_router(media_studio.router)
app.include_router(calendar_connection.router)
app.include_router(email_secretary.router)
app.include_router(hermes_ops.router)  # answers 404 unless HERMES_GATEWAY_ENABLED and HERMES_GATEWAY_KEY are set

# Public widget endpoints authenticate with the tenant's public key in the request body, not
# cookies, so wildcard CORS is safe. Per-tenant origin allow-lists are enforced in code.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token", "Authorization", "X-Voice-Session-Token"],
)


@app.middleware("http")
async def owner_boundary(request: Request, call_next):
    """Same-origin owner portal; no third-party browser access to owner APIs."""
    path = request.url.path
    if path == "/owner-ui" or path.startswith("/owner/") or path.startswith("/api/v1/device-sms/"):
        origin = request.headers.get("origin")
        if origin:
            allowed = {
                f"{request.url.scheme}://{request.url.netloc}".lower(),
                _origin_of(settings.public_base_url),
            }
            if origin.rstrip("/").lower() not in allowed:
                return Response(status_code=403, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    return await call_next(request)


# ------------------------------------------------------------------ helpers
def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


async def _tenant_for(request: Request, key: str) -> dict:
    tenant = await tenants.get_by_key(key)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown key")
    origin = request.headers.get("origin")
    allowed = tenant["allowed_origins"]
    if allowed and origin:
        permitted = {o.rstrip("/").lower() for o in allowed}
        permitted.add(_origin_of(settings.public_base_url))  # our own /demo pages
        if origin.rstrip("/").lower() not in permitted:
            raise HTTPException(status_code=403, detail="Origin not allowed")
    return tenant


def _rate_limit(request: Request, session_id: str | None = None) -> None:
    ip = request.client.host if request.client else "unknown"
    if not ip_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Too many requests, please slow down")
    if session_id and not session_limiter.check(session_id):
        raise HTTPException(status_code=429, detail="Session limit reached")


# ------------------------------------------------------------- public API
@app.get("/healthz")
async def healthz():
    await db.pool().fetchval("SELECT 1")
    return {"ok": True}


@app.get("/widget.js")
async def widget_js():
    return FileResponse(
        STATIC_DIR / "widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


class PublicTranslateRequest(BaseModel):
    locale: str = Field(min_length=2, max_length=12)
    strings: list[str] = Field(min_length=1, max_length=80)


_GOOGLE_LOCALE = {"pt-BR": "pt", "pt-PT": "pt", "zh-CN": "zh-CN", "zh-TW": "zh-TW"}


async def _google_translate(values: list[str], locale: str) -> dict[str, str]:
    code = _GOOGLE_LOCALE.get(locale, locale.split("-")[0])
    joined = "\n".join(values)
    url = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": "en", "tl": code, "dt": "t", "q": joined}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    translated = "".join(segment[0] for segment in data[0] if segment and segment[0])
    parts = translated.split("\n")
    if len(parts) == len(values):
        return dict(zip(values, parts))
    return {value: (parts[index] if index < len(parts) else value) for index, value in enumerate(values)}


_translate_hits: dict[str, list[float]] = {}


@app.post("/api/v1/translate")
async def public_translate(body: PublicTranslateRequest, request: Request):
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin and origin not in {"https://trendibizz.com", "https://www.trendibizz.com"}:
        raise HTTPException(403, "Origin not allowed")
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = [stamp for stamp in _translate_hits.get(ip, []) if now - stamp < 60]
    if len(hits) >= 30:
        raise HTTPException(429, "Too many translation requests")
    _translate_hits[ip] = hits + [now]
    locale = body.locale.strip()
    if locale == "en":
        return {"locale": locale, "strings": {source: source for source in body.strings}}
    requested = []
    for source in body.strings:
        value = source.strip()
        if value and len(value) <= 300 and value not in requested:
            requested.append(value)
    if not requested:
        return {"locale": locale, "strings": {}}
    rows = await db.pool().fetch(
        "SELECT source, translated FROM ui_translation_cache WHERE locale=$1 AND source=ANY($2::text[])",
        locale, requested)
    found = {row["source"]: row["translated"] for row in rows}
    missing = [value for value in requested if value not in found]
    if missing:
        settings = get_settings()
        if settings.cloudflare_account_id and cloudflare_auth.configured(settings):
            try:
                prompt = ("Translate these website strings into locale " + locale + ". "
                          "Keep brand names Trendi and Concierge. Return only a JSON object "
                          "with the same keys and translated values. " +
                          json.dumps({value: value for value in missing}, ensure_ascii=False))
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/run/@cf/meta/llama-3.1-8b-instruct",
                        headers={**cloudflare_auth.headers(settings), "Content-Type": "application/json"},
                        json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 4096})
                data = response.json()
                result = data.get("result") or {}
                content = (result.get("response")
                           or ((result.get("choices") or [{}])[0].get("message") or {}).get("content")
                           or "")
                content = str(content).strip()
                if not content:
                    log.warning("translation model response: %s", str(data)[:400])
                    raise RuntimeError("empty translation response")
                content = content[content.find("{"):content.rfind("}") + 1]
                translated = json.loads(content)
                if len(translated) == 1 and isinstance(next(iter(translated.values())), dict):
                    translated = next(iter(translated.values()))
                for source in missing:
                    value = str(translated.get(source, source))
                    if not value or value == source:
                        continue
                    found[source] = value
                    await db.pool().execute(
                        "INSERT INTO ui_translation_cache(locale,source,translated) VALUES($1,$2,$3) "
                        "ON CONFLICT (locale,source) DO NOTHING", locale, source, value)
            except Exception:
                log.exception("public translation failed")
        still = [value for value in missing if value not in found]
        if still:
            try:
                found.update(await _google_translate(still, locale))
                for source in still:
                    value = found.get(source, source)
                    if not value or value == source:
                        continue
                    await db.pool().execute(
                        "INSERT INTO ui_translation_cache(locale,source,translated) VALUES($1,$2,$3) "
                        "ON CONFLICT (locale,source) DO NOTHING", locale, source, value)
            except Exception:
                log.exception("google translation fallback failed")
        for source in missing:
            found.setdefault(source, source)
    return {"locale": locale, "strings": {source: found[source] for source in requested}}


@app.get("/api/v1/widget-logo")
async def widget_logo(request: Request, key: str):
    tenant = await _tenant_for(request, key)
    row = await db.pool().fetchrow("SELECT logo_data FROM media_brand WHERE tenant_id=$1", tenant["id"])
    data = row["logo_data"] if row else None
    if not data or not data.startswith("data:image/"):
        raise HTTPException(404, "Logo unavailable")
    header, encoded = data.split(",", 1)
    mime = header[5:].split(";")[0] or "image/png"
    return Response(base64.b64decode(encoded), media_type=mime,
                    headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/v1/widget-config")
async def widget_config(request: Request, key: str):
    tenant = await _tenant_for(request, key)
    result = tenants.public_view(tenant)
    brand = await db.pool().fetchrow("SELECT logo_data FROM media_brand WHERE tenant_id=$1", tenant["id"])
    if brand and brand["logo_data"]:
        result["logo_url"] = "/api/v1/widget-logo?key=" + quote_plus(key)
    result["recording_available"] = bool(settings.voice_recording_enabled and tenant.get("voice_enabled") and await channel_authorization.is_authorized(tenant["id"], "call_recording"))
    return result


class ChatRequest(BaseModel):
    key: str
    session_id: str
    message: str = Field(min_length=1, max_length=1000)
    page_url: str | None = None
    utm: dict[str, str] = {}


@app.post("/api/v1/chat")
async def chat(req: ChatRequest, request: Request):
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    try:
        result = await chat_engine.run_turn(
            tenant, session_id, "chat", req.message, page_url=req.page_url, utm=req.utm
        )
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed for tenant %s", tenant["slug"])
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable")
    return {
        "reply": result["reply"],
        "lead_captured": result["lead_captured"],
        "booking_url": result["booking_url"],
        "appointment": result["appointment"],
    }


@app.post("/api/v1/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """Server-sent token stream for the website widget (same turn semantics)."""
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)

    async def events():
        try:
            async for event in chat_engine.run_turn_stream(
                tenant, session_id, "chat", req.message, page_url=req.page_url, utm=req.utm
            ):
                yield "data: " + json.dumps(event, default=str) + "\n\n"
        except llm.LLMNotConfigured:
            yield 'data: {"type":"error","message":"AI is not configured"}\n\n'
        except Exception:
            log.exception("chat stream failed for tenant %s", tenant["slug"])
            yield 'data: {"type":"error"}\n\n'

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _twiml(text: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response>'
    if text:
        body += f"<Message>{xml_escape(text[:1500])}</Message>"
    body += "</Response>"
    return Response(content=body, media_type="application/xml")


@app.post("/api/v1/sms/{public_key}")
async def sms_inbound(public_key: str, request: Request):
    """Twilio inbound-SMS webhook: a visitor texts the client's number and the AI replies."""
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

    if not await channel_authorization.is_authorized(tenant["id"], "sms_read"):
        raise HTTPException(status_code=403, detail="Business has not authorized inbound SMS")
    sender = normalize_phone(params.get("From", ""), casetimeline.tenant_country_code(tenant))
    body = (params.get("Body") or "").strip()
    if not sender or not body:
        return _twiml("")
    # Twilio sends its own opt-out confirmation, so STOP gets no reply of ours here.
    return _twiml(await _sms_reply(tenant, sender, body, confirm_stop=False))


@app.post("/api/v1/smsgate/{public_key}")
async def smsgate_inbound(public_key: str, request: Request):
    """Webhook for the self-hosted Android SMS gateway (event sms:received). The reply is sent as a
    new text, because the gateway has no reply-in-response mechanism like TwiML."""
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
    if not isinstance(envelope, dict) or envelope.get("event") != "sms:received":
        return {"ok": True}  # delivery receipts and pings are acknowledged and ignored

    if not await channel_authorization.is_authorized(tenant["id"], "sms_read"):
        raise HTTPException(status_code=403, detail="Business has not authorized inbound SMS")
    payload = envelope.get("payload") or {}
    sender = normalize_phone(payload.get("sender") or payload.get("phoneNumber") or "", casetimeline.tenant_country_code(tenant))
    body = (payload.get("message") or "").strip()
    if not sender or not body:
        return {"ok": True}

    reply = await _sms_reply(tenant, sender, body, confirm_stop=True)
    if reply:
        events.spawn(_send_reply(tenant, sender, reply))
    return {"ok": True}


async def _send_reply(tenant: dict, to: str, text: str) -> None:
    try:
        await sms.send_sms(to, text, tenant.get("sms_from"))
    except Exception:
        log.exception("sms reply failed for %s", tenant["slug"])


async def _sms_reply(tenant: dict, sender: str, body: str, confirm_stop: bool) -> str:
    """Shared inbound-text logic for every provider. Returns the reply text, or "" for no reply."""
    command = body.upper()
    if command in STOP_WORDS:
        await outbox.opt_out(tenant["id"], sender)
        return f"You're unsubscribed from {tenant['name']} messages. Reply START to resume." if confirm_stop else ""
    if command in START_WORDS:
        await outbox.opt_in(tenant["id"], sender)
        return f"You're subscribed to messages from {tenant['name']} again. Reply STOP to opt out."
    if command == "HELP":
        return f"{tenant['name']} AI assistant. Msg&data rates may apply. Reply STOP to opt out."
    if await outbox.is_opted_out(tenant["id"], sender):
        return ""

    session_id = "sms" + re.sub(r"\D", "", sender)
    if not sms_limiter.check(session_id):
        return ""
    conversation_id = await convo.get_or_create(tenant, session_id, "sms", None, None)
    await enquiries.capture(tenant, "sms", session_id, body,
                            conversation_id=conversation_id, phone=sender, consent_contact=True)
    try:
        result = await chat_engine.run_turn(tenant, session_id, "sms", body[:1000], sender_phone=sender)
    except Exception:
        log.exception("sms turn failed for %s", tenant["slug"])
        return "Sorry, I'm having trouble right now. The team will get back to you."
    return result["reply"]


class VoiceTokenRequest(BaseModel):
    key: str
    session_id: str
    recording_consent: bool = False


@app.post("/api/v1/voice/token")
async def voice_token(req: VoiceTokenRequest, request: Request):
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
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


@app.post("/api/v1/tools/{name}")
async def tool_endpoint(name: str, req: ToolRequest, request: Request):
    """Called by the widget when Grok Voice invokes a function."""
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
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
    return await run_tool(tenant, name, req.args, ctx)


class VoiceLogRequest(BaseModel):
    key: str
    session_id: str
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(min_length=1, max_length=4000)
    page_url: str | None = None
    utm: dict[str, str] = {}


@app.post("/api/v1/voice/log")
async def voice_log(req: VoiceLogRequest, request: Request):
    session_id = convo.clean_session(req.session_id)
    _rate_limit(request, session_id)
    tenant = await _tenant_for(request, req.key)
    conversation_id = await convo.get_or_create(tenant, session_id, "voice", req.page_url, req.utm)
    await convo.save_message(conversation_id, "user" if req.role == "user" else "assistant", req.text)
    return {"ok": True}


@app.post("/api/v1/voice/sessions/{session_id}/recording")
async def voice_recording_upload(session_id: uuid.UUID, request: Request):
    session = await voice_records.authenticate(session_id, request.headers.get("x-voice-session-token", ""))
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > voice_records.MAX_AUDIO:
            raise HTTPException(413, "Recording exceeds the size limit")
    return await voice_records.store_audio(session, bytes(body), request.headers.get("content-type", ""))


@app.post("/api/v1/voice/sessions/{session_id}/finish")
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
        "Content-Disposition": 'inline; filename="'+filename+'"',
    })


@app.get("/api/v1/voice/recordings/shared/{token}")
async def shared_voice_recording(token: str):
    row = await voice_records.shared_audio(token)
    return private_audio_response(row, "concierge-recording." + row["mime_type"].split("/")[1])


# -------------------------------------------------------------- demo page
@app.get("/demo/{slug}", response_class=HTMLResponse)
async def demo_page(slug: str, presenter: int = 0):
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown demo")

    excerpt = await db.pool().fetchval(
        "SELECT content FROM chunks WHERE tenant_id = $1 ORDER BY id LIMIT 1", tenant["id"]
    )
    name = html.escape(tenant["name"])
    excerpt_html = html.escape((excerpt or "")[:700]).replace("\n", "<br>")
    site = tenant.get("site_url") or ""
    site_html = html.escape(site) if site.startswith(("http://", "https://")) else ""

    questions = tenant["demo_questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    panel = ""
    if presenter and questions:
        items = "".join(f"<li>{html.escape(q)}</li>" for q in questions)
        panel = f"<aside><h2>Questions to ask</h2><ol>{items}</ol></aside>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - AI guide demo</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;color:#111;background:#fafafa}}
 header{{padding:24px;background:{html.escape(tenant['accent_color'])};color:#fff}}
 main{{max-width:760px;margin:32px auto;padding:0 16px;line-height:1.6}}
 aside{{position:fixed;left:16px;bottom:16px;max-width:380px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;font-size:14px}}
 small{{color:#666}}
</style></head>
<body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">Sandbox preview of your AI guide{' - ' + site_html if site_html else ''}</small></header>
<main><p>{excerpt_html}</p></main>
{panel}
<script src="/widget.js" data-key="{html.escape(tenant['public_key'])}" data-autoopen="1" defer></script>
</body></html>"""
    return HTMLResponse(page)


# ------------------------------------------------------------ client report
async def _stats(tenant: dict, days: int) -> dict:
    pool = db.pool()
    days = min(max(days, 1), 365)
    convs = await pool.fetch(
        """
        SELECT channel, count(*) AS conversations
        FROM conversations
        WHERE tenant_id = $1 AND channel <> 'eval' AND started_at > now() - make_interval(days => $2)
        GROUP BY channel
        """,
        tenant["id"], days,
    )
    leads_by_status = await pool.fetch(
        "SELECT status, count(*) AS n FROM leads WHERE tenant_id = $1 "
        "AND created_at > now() - make_interval(days => $2) GROUP BY status",
        tenant["id"], days,
    )
    appointments = await pool.fetchval(
        "SELECT count(*) FROM appointments WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)",
        tenant["id"], days,
    )
    guard_hits = await pool.fetchval(
        """
        SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id
        WHERE c.tenant_id = $1 AND m.flag = 'quote_guard' AND m.created_at > now() - make_interval(days => $2)
        """,
        tenant["id"], days,
    )
    sent = await pool.fetch(
        "SELECT channel, count(*) AS n FROM outbox WHERE tenant_id = $1 AND status = 'sent' "
        "AND created_at > now() - make_interval(days => $2) GROUP BY channel",
        tenant["id"], days,
    )
    daily = await pool.fetch(
        """
        SELECT d::date AS day,
               (SELECT count(*) FROM conversations c WHERE c.tenant_id = $1 AND c.channel <> 'eval' AND c.started_at::date = d::date) AS conversations,
               (SELECT count(*) FROM leads l WHERE l.tenant_id = $1 AND l.created_at::date = d::date) AS leads
        FROM generate_series(now() - make_interval(days => $2 - 1), now(), interval '1 day') d
        ORDER BY day
        """,
        tenant["id"], days,
    )
    status_counts = {r["status"]: r["n"] for r in leads_by_status}
    total_leads = sum(status_counts.values())
    total_convs = sum(r["conversations"] for r in convs)
    value_each = tenant.get("lead_value_cents") or 0
    won_value = await pool.fetchval(
        "SELECT COALESCE(sum(value_cents), 0) FROM leads WHERE tenant_id = $1 AND status = 'won' "
        "AND updated_at > now() - make_interval(days => $2)",
        tenant["id"], days,
    )
    return {
        "days": days,
        "conversations": total_convs,
        "by_channel": {r["channel"]: r["conversations"] for r in convs},
        "leads": total_leads,
        "leads_by_status": status_counts,
        "lead_rate": round(total_leads / total_convs, 3) if total_convs else 0,
        "appointments": appointments,
        "estimated_pipeline_cents": total_leads * value_each,
        "won_value_cents": won_value,
        "quote_guard_interventions": guard_hits,
        "messages_sent": {r["channel"]: r["n"] for r in sent},
        "daily": [dict(r) for r in daily],
    }


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


@app.get("/report/{token}", response_class=HTMLResponse)
async def client_report(token: str, days: int = 30):
    """Read-only monthly report for the client. The unguessable token is the credential."""
    tenant = await tenants.get_by_report_token(token)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    s = await _stats(tenant, days)

    peak = max([d["leads"] for d in s["daily"]] + [d["conversations"] for d in s["daily"]] + [1])
    bar_w = 600 / max(len(s["daily"]), 1)
    bars = []
    for i, d in enumerate(s["daily"]):
        x = i * bar_w
        h_c = 100 * d["conversations"] / peak
        h_l = 100 * d["leads"] / peak
        bars.append(
            f'<rect x="{x:.1f}" y="{110 - h_c:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_c:.1f}" fill="#94a3b8"/>'
            f'<rect x="{x + bar_w * 0.45:.1f}" y="{110 - h_l:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_l:.1f}" fill="{html.escape(tenant["accent_color"])}"/>'
        )
    leads = await db.pool().fetch(
        "SELECT name, message, channel, status, score_label, created_at FROM leads WHERE tenant_id = $1 "
        "AND created_at > now() - make_interval(days => $2) ORDER BY created_at DESC LIMIT 25",
        tenant["id"], s["days"],
    )
    rows = "".join(
        f"<tr><td>{r['created_at']:%b %d}</td><td>{html.escape((r['name'] or 'Visitor').split(' ')[0])}</td>"
        f"<td>{html.escape(r['message'][:140])}</td><td>{html.escape(r['channel'])}</td><td>{html.escape(r['status'])}</td>"
        f"<td>{html.escape((r['score_label'] or 'cold').title())}</td></tr>"
        for r in leads
    )
    card = lambda label, value: f'<div class="c"><b>{value}</b><span>{label}</span></div>'  # noqa: E731
    cards = "".join([
        card("Visitor conversations", s["conversations"]),
        card("Leads captured", s["leads"]),
        card("Appointments booked", s["appointments"]),
        card("Estimated pipeline", _money(s["estimated_pipeline_cents"]) if s["estimated_pipeline_cents"] else "-"),
    ])
    name = html.escape(tenant["name"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{name} - AI guide report</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#111}}
 header{{background:{html.escape(tenant['accent_color'])};color:#fff;padding:20px 24px}}
 main{{max-width:760px;margin:24px auto;padding:0 16px}}
 .g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
 .c{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8}}
 .c b{{display:block;font-size:26px}} .c span{{color:#666;font-size:13px}}
 section{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8;margin-top:16px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px;border-bottom:1px solid #eee}}
 small{{color:#666}}
</style></head><body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">AI guide results - last {s['days']} days</small></header>
<main>
<div class="g">{cards}</div>
<section><b>Daily activity</b> <small>grey = conversations, colour = leads</small>
<svg viewBox="0 0 600 115" width="100%" role="img" aria-label="Daily conversations and leads">{''.join(bars)}</svg></section>
<section><b>Recent leads</b><table><tr><th>Date</th><th>Who</th><th>What they wanted</th><th>Via</th><th>Status</th><th>Interest</th></tr>{rows or '<tr><td colspan=6>No leads yet.</td></tr>'}</table></section>
<p><small>Estimated pipeline = leads x the average lead value agreed with your provider. Contact details are not shown on this page.</small></p>
</main></body></html>"""
    return HTMLResponse(page)


# -------------------------------------------------------------------- admin
admin = [Depends(require_admin)]


@app.get("/admin-ui")
async def admin_ui():
    """Static dashboard shell. It holds no data; the page asks for the admin token and calls /admin/*."""
    return FileResponse(STATIC_DIR / "admin.html", media_type="text/html", headers={"Cache-Control": "no-store"})


class TenantCreate(BaseModel):
    name: str
    site_url: str | None = None
    slug: str | None = None
    persona: str = ""
    greeting: str = ""
    booking_url: str | None = None
    lead_webhook_url: str | None = None
    incentive: str = ""
    allowed_origins: list[str] = []


class TenantUpdate(BaseModel):
    name: str | None = None
    site_url: str | None = None
    allowed_origins: list[str] | None = None
    persona: str | None = None
    greeting: str | None = None
    cta_text: str | None = None
    accent_color: str | None = None
    voice: str | None = None
    voice_enabled: bool | None = None
    phone_enabled: bool | None = None
    phone_daily_limit: int | None = Field(default=None, ge=0, le=100_000)
    voice_daily_limit: int | None = Field(default=None, ge=0, le=100_000)
    booking_url: str | None = None
    lead_webhook_url: str | None = None
    incentive: str | None = None
    timezone: str | None = None
    business_hours: dict[str, list[list[str]]] | None = None
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    min_notice_hours: int | None = Field(default=None, ge=0, le=720)
    max_days_ahead: int | None = Field(default=None, ge=1, le=365)
    native_booking: bool | None = None
    notify_email: str | None = None
    notify_phone: str | None = Field(default=None, max_length=32)
    owner_call_phone: str | None = Field(default=None, max_length=32)   # number a take-over/ring-first rings; falls back to notify_phone
    inbound_ack: bool | None = None   # acknowledge verified inbound email with a reference (opt-in)
    inbound_ack_text: str | None = Field(default=None, max_length=600)
    owner_text_only: bool | None = None   # owner works in writing only: never ring or transfer to a human
    sms_enabled: bool | None = None
    sms_from: str | None = None
    lead_sms_template: str | None = None
    review_url: str | None = None
    lead_value_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    sla_minutes: int | None = Field(default=None, ge=0, le=1440)       # 0 = response alerts off
    sla_min_score: int | None = Field(default=None, ge=0, le=100)
    campaigns_enabled: bool | None = None
    weekly_digest: bool | None = None                                  # Monday summary email to notify_email
    scoring: dict[str, int] | None = None                              # {} resets to the defaults

    @field_validator("scoring")
    @classmethod
    def _scoring(cls, value):
        if value is None:
            return value
        return scoring.validate_overrides(value)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value):
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError("unknown IANA timezone, e.g. America/Chicago")
        return value

    @field_validator("lead_sms_template")
    @classmethod
    def _template(cls, value):
        if value is None:
            return value
        try:
            value.format(first="A", name="A", business="A")
        except Exception:
            raise ValueError("template may only use {first}, {name} and {business}")
        return value

    @field_validator("business_hours")
    @classmethod
    def _hours(cls, value):
        if value is None:
            return value
        for key, windows in value.items():
            if key not in DAYS:
                raise ValueError(f"unknown day '{key}' (use {', '.join(DAYS)})")
            for window in windows:
                if len(window) != 2 or not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", w) for w in window):
                    raise ValueError("each window must be [\"HH:MM\", \"HH:MM\"]")
                if window[0] >= window[1]:
                    raise ValueError("a window must open before it closes")
        return value


class CloneRequest(BaseModel):
    name: str
    site_url: str | None = None
    slug: str | None = None


class LeadUpdate(BaseModel):
    status: Literal["new", "contacted", "booked", "won", "lost"] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    value_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    lost_reason: str | None = Field(default=None, max_length=300)   # only used together with status = lost
    next_action_at: datetime | None = None                          # also moves the lead's follow-up to-do

    @field_validator("next_action_at")
    @classmethod
    def _aware(cls, value):
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class AppointmentUpdate(BaseModel):
    status: Literal["booked", "completed", "cancelled", "no_show"]


def _with_snippet(tenant: dict) -> dict:
    base = settings.public_base_url
    return {
        **tenant,
        "embed_snippet": f'<script src="{base}/widget.js" data-key="{tenant["public_key"]}" defer></script>',
        "demo_url": f"{base}/demo/{tenant['slug']}?presenter=1",
        "report_url": f"{base}/report/{tenant['report_token']}",
        "sms_webhook_url": f"{base}/api/v1/sms/{tenant['public_key']}",
        "calendar_url": f"{base}/api/v1/calendar/{tenant['calendar_token']}.ics" if tenant.get("calendar_token") else None,
    }


async def _require_tenant(slug: str) -> dict:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


@app.post("/admin/tenants", dependencies=admin)
async def admin_create_tenant(body: TenantCreate):
    data = body.model_dump()
    tenant = await tenants.create(data.pop("name"), data.pop("site_url"), slug=data.pop("slug"), **data)
    try:
        tenant = await reply_address.ensure(tenant)
    except Exception:  # noqa: BLE001 - tenant exists; the operator can retry routing
        log.exception("reply address setup failed for %s", tenant["slug"])
    return _with_snippet(tenant)


@app.get("/admin/tenants", dependencies=admin)
async def admin_list_tenants():
    return [_with_snippet(t) for t in await tenants.list_all()]


@app.get("/admin/status", dependencies=admin)
async def admin_status():
    counts = await db.pool().fetchrow(
        "SELECT (SELECT count(*) FROM tenants) AS tenants, "
        "(SELECT count(*) FROM leads) AS leads, "
        "(SELECT count(*) FROM quotations) AS quotations, "
        "(SELECT count(*) FROM media_assets) AS media_assets, "
        "(SELECT count(*) FROM design_uploads) AS designs, "
        "pg_database_size(current_database()) AS database_bytes")
    backups = []
    root = Path("/backups")
    if root.is_dir():
        for item in sorted(root.glob("trendi-backup-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)[:14]:
            stat = item.stat()
            backups.append({"name": item.name, "bytes": stat.st_size, "modified": int(stat.st_mtime)})
    return {"counts": dict(counts), "backups": backups}


@app.get("/admin/outbound/status", dependencies=admin)
async def admin_outbound_status():
    """Paused or not, volumes against the limits, and what the flood guard blocked."""
    return await flood_guard.status()


@app.post("/admin/outbound/pause", dependencies=admin)
async def admin_outbound_pause():
    """Kill switch: stop ALL email and text sending now. Everything stays queued."""
    await flood_guard.set_paused(True, "admin")
    return {"paused": True}


@app.post("/admin/outbound/resume", dependencies=admin)
async def admin_outbound_resume():
    await flood_guard.set_paused(False, "admin")
    return {"paused": False}


@app.post("/admin/tenants/{slug}/rotate-key", dependencies=admin)
async def admin_rotate_key(slug: str):
    """Retire a business's install key: the old snippet stops working at once.

    The key in the embed snippet had no way to be replaced other than deleting the business, so a
    retired prototype kept answering and kept taking enquiries nobody read.
    """
    tenant = await db.pool().fetchrow("SELECT id FROM tenants WHERE slug=$1", slug)
    if not tenant:
        raise HTTPException(404, "No such business")
    key = await tenants.rotate_key(tenant["id"])
    base = get_settings().public_base_url.rstrip("/")
    return {"slug": slug, "public_key": key,
            "embed_snippet": f'<script src="{base}/widget.js" data-key="{key}" defer></script>'}


@app.get("/admin/tenants/{slug}", dependencies=admin)
async def admin_get_tenant(slug: str):
    tenant = await tenants.ensure_calendar_token(await _require_tenant(slug))
    chunks = await db.pool().fetchval("SELECT count(*) FROM chunks WHERE tenant_id = $1", tenant["id"])
    return {**_with_snippet(tenant), "chunk_count": chunks}


@app.patch("/admin/tenants/{slug}", dependencies=admin)
async def admin_update_tenant(slug: str, body: TenantUpdate, force: bool = False):
    current = await _require_tenant(slug)
    changes = body.model_dump(exclude_unset=True)
    # Go-live gate: never switch a phone line on for a business whose owner cannot be told about
    # the enquiries it takes. `?force=true` is the operator's explicit override.
    if changes.get("phone_enabled") and not current.get("phone_enabled") and not force:
        blockers = await channel_health.go_live_blockers({**current, **changes})
        if blockers:
            raise HTTPException(409, {"error": "alerts_not_proven", "blockers": blockers})
    updated = await tenants.update(slug, changes)
    if updated.get("notify_email") and not updated.get("reply_address"):
        try:
            updated = await reply_address.ensure(updated)
        except Exception:  # noqa: BLE001
            log.exception("reply address setup failed for %s", slug)
    return _with_snippet(updated)


@app.delete("/admin/tenants/{slug}", dependencies=admin)
async def admin_delete_tenant(slug: str):
    if not await tenants.delete(slug):
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return {"ok": True}


@app.post("/admin/tenants/{slug}/clone", dependencies=admin)
async def admin_clone_tenant(slug: str, body: CloneRequest):
    """Snapshot: copy settings (persona, hours, SMS template...) to a new client. No knowledge or contacts."""
    source = await _require_tenant(slug)
    return _with_snippet(await tenants.clone(source, body.name, body.site_url, body.slug))


class CrawlRequest(BaseModel):
    max_pages: int = Field(default=40, ge=1, le=300)


async def _crawl_job(tenant: dict, max_pages: int) -> None:
    try:
        await ingest.ingest_site(tenant, max_pages=max_pages)
    except Exception:
        log.exception("crawl failed for %s", tenant["slug"])


@app.post("/admin/tenants/{slug}/crawl", dependencies=admin, status_code=202)
async def admin_crawl(slug: str, body: CrawlRequest, background: BackgroundTasks):
    tenant = await _require_tenant(slug)
    if not tenant.get("site_url"):
        raise HTTPException(status_code=400, detail="Tenant has no site_url")
    background.add_task(_crawl_job, tenant, body.max_pages)
    return {"status": "started", "hint": "Check chunk_count on GET /admin/tenants/{slug}"}


class IngestTextRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80, pattern="^[A-Za-z0-9_.-]+$")
    title: str = ""
    text: str = Field(min_length=1, max_length=200_000)


@app.post("/admin/tenants/{slug}/ingest-text", dependencies=admin)
async def admin_ingest_text(slug: str, body: IngestTextRequest):
    tenant = await _require_tenant(slug)
    return await ingest.ingest_text(tenant, body.label, body.text, body.title)


@app.post("/admin/tenants/{slug}/demo-questions", dependencies=admin)
async def admin_demo_questions(slug: str):
    tenant = await _require_tenant(slug)
    try:
        return {"questions": await ingest.generate_demo_questions(tenant)}
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")


@app.get("/admin/tenants/{slug}/leads", dependencies=admin)
async def admin_leads(slug: str, limit: int = 100, min_score: int = 0):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM leads WHERE tenant_id = $1 AND score >= $3 ORDER BY created_at DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 500), max(min_score, 0),
    )
    return [dict(r) for r in rows]


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: Literal["sms", "email"]
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=600)
    older_than_days: int = Field(default=30, ge=0, le=3650)
    statuses: list[Literal["new", "contacted", "booked", "won", "lost"]] = ["new", "contacted", "lost"]
    min_score: int = Field(default=0, ge=0, le=100)
    max_recipients: int | None = Field(default=None, ge=1)


class CampaignSend(BaseModel):
    expected_recipients: int = Field(ge=0)


class MarketingConsent(BaseModel):
    consent: bool
    basis: str = Field(min_length=5, max_length=300)  # where the consent came from, kept as the audit trail


def _campaign_view(campaign: dict) -> dict:
    view = dict(campaign)
    if isinstance(view.get("filters"), str):
        view["filters"] = json.loads(view["filters"])
    return view


async def _require_campaign(campaign_id: int) -> tuple[dict, dict]:
    campaign = await campaigns.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Unknown campaign")
    return campaign, await tenants.get_by_id(campaign["tenant_id"])


@app.post("/admin/tenants/{slug}/campaigns", dependencies=admin, status_code=201)
async def admin_create_campaign(slug: str, body: CampaignCreate):
    """Create a DRAFT campaign and return who it would reach. Nothing is sent."""
    tenant = await _require_tenant(slug)
    try:
        campaign = await campaigns.create(
            tenant, body.name, body.channel, body.subject, body.body,
            body.model_dump(include={"older_than_days", "statuses", "min_score", "max_recipients"}),
        )
    except campaigns.CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"campaign": _campaign_view(campaign), "preview": await campaigns.preview(tenant, campaign)}


@app.get("/admin/tenants/{slug}/campaigns", dependencies=admin)
async def admin_list_campaigns(slug: str):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM campaigns WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 100", tenant["id"])
    return [{**_campaign_view(dict(r)), "delivery": await campaigns.stats(r["id"])} for r in rows]


@app.get("/admin/campaigns/{campaign_id}/preview", dependencies=admin)
async def admin_preview_campaign(campaign_id: int):
    campaign, tenant = await _require_campaign(campaign_id)
    return await campaigns.preview(tenant, campaign)


@app.post("/admin/campaigns/{campaign_id}/send", dependencies=admin)
async def admin_send_campaign(campaign_id: int, body: CampaignSend):
    """Queue the campaign. `expected_recipients` must match the preview's recipient count."""
    campaign, tenant = await _require_campaign(campaign_id)
    try:
        return await campaigns.send(tenant, campaign, body.expected_recipients)
    except campaigns.CampaignError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Audience changed") else 400, detail=str(exc))


@app.post("/admin/campaigns/{campaign_id}/cancel", dependencies=admin)
async def admin_cancel_campaign(campaign_id: int):
    campaign, _ = await _require_campaign(campaign_id)
    return {"cancelled_pending": await campaigns.cancel(campaign)}


@app.get("/admin/campaigns/{campaign_id}", dependencies=admin)
async def admin_get_campaign(campaign_id: int):
    campaign, _ = await _require_campaign(campaign_id)
    return {**_campaign_view(campaign), "delivery": await campaigns.stats(campaign_id)}


@app.patch("/admin/leads/{lead_id}/marketing-consent", dependencies=admin)
async def admin_marketing_consent(lead_id: str, body: MarketingConsent):
    """Record (or withdraw) marketing consent for a lead, with where it came from."""
    try:
        row = await db.pool().fetchrow(
            "UPDATE leads SET consent_marketing = $2, consent_marketing_basis = $3, "
            "consent_marketing_at = CASE WHEN $2 THEN now() END, updated_at = now() WHERE id = $1::uuid "
            "RETURNING id, consent_marketing, consent_marketing_basis, consent_marketing_at",
            lead_id, body.consent, body.basis.strip(),
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown lead")
    return dict(row)


def _plain_page(title: str, body_html: str, status: int = 200) -> HTMLResponse:
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#111}"
        "button{font:inherit;padding:.7rem 1.2rem;border-radius:8px;border:0;background:#111;color:#fff;cursor:pointer}</style>"
        f"</head><body><h1>{html.escape(title)}</h1>{body_html}</body></html>"
    )
    return HTMLResponse(page, status_code=status)


@app.get("/api/v1/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_page(token: str):
    """Confirm page. Opening the link does nothing by itself, so mail scanners cannot unsubscribe anyone."""
    if unsub.read_token(token) is None:
        return _plain_page("This link is not valid", "<p>It may be incomplete. Reply to the email and we will remove you.</p>", 404)
    return _plain_page(
        "Unsubscribe",
        '<p>Stop receiving promotional messages from this business?</p><form method="post"><button>Unsubscribe</button></form>',
    )


@app.post("/api/v1/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_do(token: str):
    """Performs the unsubscribe. Also serves mail apps' one-click unsubscribe (RFC 8058)."""
    result = await campaigns.unsubscribe(token)
    if result is None:
        return _plain_page("This link is not valid", "<p>Reply to the email and we will remove you.</p>", 404)
    return _plain_page(
        "You are unsubscribed",
        f"<p>{html.escape(result['tenant_name'])} will not send you promotional messages again.</p>",
    )


@app.get("/admin/tenants/{slug}/scoring", dependencies=admin)
async def admin_scoring(slug: str):
    """The scoring weights in force for this client, with defaults, for the dashboard editor."""
    tenant = await _require_tenant(slug)
    return {"weights": scoring.describe(tenant)}


@app.post("/admin/tenants/{slug}/rescore", dependencies=admin)
async def admin_rescore(slug: str):
    """Recompute every lead's score with the client's current weights."""
    tenant = await _require_tenant(slug)
    return await scoring.rescore_tenant(tenant)


@app.get("/admin/tenants/{slug}/sla", dependencies=admin)
async def admin_sla(slug: str):
    """Response-time settings and the leads currently waiting longer than the target."""
    tenant = await _require_tenant(slug)
    waiting = await sla.overdue(tenant)
    return {
        "sla_minutes": tenant.get("sla_minutes") or 0,
        "sla_min_score": tenant.get("sla_min_score") if tenant.get("sla_min_score") is not None else 70,
        "waiting": [
            {
                "id": str(w["id"]), "name": w["name"], "phone": w["phone"], "email": w["email"],
                "message": w["message"], "channel": w["channel"], "score": w["score"],
                "score_label": w["score_label"], "reasons": scoring.reasons_of(w),
                "minutes_waiting": w["minutes_waiting"], "alerted": w["sla_alerted_at"] is not None,
                "created_at": w["created_at"].isoformat(),
            }
            for w in waiting
        ],
    }


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    due_at: datetime | None = None
    lead_id: str | None = None

    @field_validator("due_at")
    @classmethod
    def _aware(cls, value):
        return _aware(value)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    status: Literal["open", "done"] | None = None

    @field_validator("due_at")
    @classmethod
    def _aware(cls, value):
        return _aware(value)


def _aware(value):
    """A date typed without a timezone is taken as UTC, so it can never be misread as local time."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@app.get("/admin/tenants/{slug}/tasks", dependencies=admin)
async def admin_list_tasks(slug: str, status: Literal["open", "done", "all"] = "open"):
    tenant = await _require_tenant(slug)
    return await tasks.list_tasks(tenant["id"], status)


@app.post("/admin/tenants/{slug}/tasks", dependencies=admin, status_code=201)
async def admin_create_task(slug: str, body: TaskCreate):
    tenant = await _require_tenant(slug)
    if body.lead_id:
        try:
            found = await db.pool().fetchval("SELECT 1 FROM leads WHERE id = $1::uuid AND tenant_id = $2", body.lead_id, tenant["id"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid lead id")
        if not found:
            raise HTTPException(status_code=404, detail="Unknown lead")
    try:
        return await tasks.create(tenant["id"], body.title, body.notes, body.due_at, lead_id=body.lead_id)
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/admin/tasks/{task_id}", dependencies=admin)
async def admin_update_task(task_id: int, body: TaskUpdate):
    try:
        row = await tasks.update(task_id, body.model_dump(exclude_unset=True))
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown to-do")
    return row


@app.delete("/admin/tasks/{task_id}", dependencies=admin)
async def admin_delete_task(task_id: int):
    if not await tasks.delete(task_id):
        raise HTTPException(status_code=404, detail="Unknown to-do")
    return {"deleted": True}


@app.get("/admin/tenants/{slug}/pipeline", dependencies=admin)
async def admin_pipeline(slug: str):
    return await sales.pipeline(await _require_tenant(slug))


@app.get("/admin/tenants/{slug}/sales-summary", dependencies=admin)
async def admin_sales_summary(slug: str, days: int = 7):
    return await sales.summary(await _require_tenant(slug), min(max(days, 1), 365))


@app.get("/api/v1/calendar/{token}.ics")
async def calendar_feed(token: str):
    """Read-only appointment feed to subscribe to from Google / Apple / Outlook Calendar. The token is the credential."""
    tenant = await tenants.get_by_calendar_token(token)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown calendar")
    rows = await db.pool().fetch(
        "SELECT * FROM appointments WHERE tenant_id = $1 AND starts_at > now() - interval '30 days' ORDER BY starts_at",
        tenant["id"],
    )
    return Response(
        content=ical.build(tenant, [dict(r) for r in rows]),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.patch("/admin/leads/{lead_id}", dependencies=admin)
async def admin_update_lead(lead_id: str, body: LeadUpdate):
    data = body.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    status = data.pop("status", None)
    reason = data.pop("lost_reason", "") or ""
    row = None
    try:
        if data:
            parts = [f"{col} = ${i}" for i, col in enumerate(data, start=2)]
            row = await db.pool().fetchrow(
                f"UPDATE leads SET {', '.join(parts)}, updated_at = now() WHERE id = $1::uuid RETURNING *",
                lead_id, *data.values(),
            )
            if row is None:
                raise LookupError
        if status:
            row = await sales.change_status(lead_id, status, reason)  # records history, tidies the follow-up
            if row is None:
                raise LookupError
        if "next_action_at" in data and row is not None:
            await tasks.set_follow_up_due(dict(row), data["next_action_at"])
    except LookupError:
        raise HTTPException(status_code=404, detail="Unknown lead")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    return dict(row)


@app.get("/admin/tenants/{slug}/appointments", dependencies=admin)
async def admin_appointments(slug: str, status: str | None = None, limit: int = 100):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM appointments WHERE tenant_id = $1 AND ($2::text IS NULL OR status = $2) "
        "ORDER BY starts_at DESC LIMIT $3",
        tenant["id"], status, min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.patch("/admin/appointments/{appointment_id}", dependencies=admin)
async def admin_update_appointment(appointment_id: str, body: AppointmentUpdate):
    try:
        row = await db.pool().fetchrow(
            "UPDATE appointments SET status = $2 WHERE id = $1::uuid RETURNING *", appointment_id, body.status
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment id")
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown appointment")
    appt = dict(row)
    tenant = await tenants.get_by_id(appt["tenant_id"])
    await automation.on_appointment_status(tenant, appt, body.status)
    if body.status in ("cancelled", "no_show"):
        await calendar_connection.sync_one(appt["id"])
    return appt


@app.get("/admin/tenants/{slug}/outbox", dependencies=admin)
async def admin_outbox(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT id, kind, channel, to_addr, status, attempts, last_error, send_at, sent_at "
        "FROM outbox WHERE tenant_id = $1 ORDER BY id DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@app.get("/admin/tenants/{slug}/conversations", dependencies=admin)
async def admin_conversations(slug: str, limit: int = 50):
    """Recent conversations with their transcripts - review these monthly to improve the knowledge base."""
    tenant = await _require_tenant(slug)
    convs = await db.pool().fetch(
        "SELECT * FROM conversations WHERE tenant_id = $1 AND channel <> 'eval' ORDER BY started_at DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 200),
    )
    out = []
    for conv in convs:
        msgs = await db.pool().fetch(
            "SELECT role, content, flag, created_at FROM messages WHERE conversation_id = $1 ORDER BY id",
            conv["id"],
        )
        out.append({**dict(conv), "messages": [dict(m) for m in msgs]})
    return out


@app.get("/admin/tenants/{slug}/stats", dependencies=admin)
async def admin_stats(slug: str, days: int = 30):
    return await _stats(await _require_tenant(slug), days)



@app.get("/admin/capabilities", dependencies=admin)
async def admin_capabilities():
    return {"email_drafts": settings.email_drafts_enabled}


# ------------------------------------------- email draft approval (disabled by default)
class EmailDraftCreate(BaseModel):
    sender: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="", max_length=250)
    inbound_body: str = Field(min_length=1, max_length=20000)
    reply_body: str | None = Field(default=None, max_length=10000)
    source_id: str = Field(default="", max_length=500)
    generate: bool = False


class EmailDraftRevision(BaseModel):
    reply_body: str = Field(min_length=1, max_length=10000)


class SenderRule(BaseModel):
    pattern: str = Field(min_length=3, max_length=320)
    action: Literal["allow", "block"]


def _email_feature_gate():
    if not settings.email_drafts_enabled:
        raise HTTPException(status_code=503, detail="Email draft workflow is disabled")


@app.get("/admin/tenants/{slug}/email-drafts", dependencies=admin)
async def admin_email_drafts(slug: str, status: Literal["draft", "approved", "discarded", "all"] = "draft"):
    _email_feature_gate()
    tenant = await _require_tenant(slug)
    return await email_drafts.list_drafts(tenant["id"], status)


@app.post("/admin/tenants/{slug}/email-drafts", dependencies=admin, status_code=201)
async def admin_email_draft_create(slug: str, body: EmailDraftCreate):
    _email_feature_gate()
    tenant = await _require_tenant(slug)
    if body.generate and body.reply_body:
        raise HTTPException(status_code=400, detail="Choose generated or manual draft")
    if not body.generate and not body.reply_body:
        raise HTTPException(status_code=400, detail="Provide reply_body or request generation")
    try:
        reply = (
            await email_drafts.propose(tenant, body.sender, body.subject, body.inbound_body)
            if body.generate else body.reply_body
        )
        return await email_drafts.create(
            tenant["id"], body.sender, body.subject, body.inbound_body,
            reply, body.source_id,
        )
    except email_drafts.DraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI email drafting is not configured")


@app.patch("/admin/tenants/{slug}/email-drafts/{draft_id}", dependencies=admin)
async def admin_email_draft_revise(slug: str, draft_id: int, body: EmailDraftRevision):
    _email_feature_gate()
    tenant = await _require_tenant(slug)
    try:
        result = await email_drafts.revise(tenant["id"], draft_id, body.reply_body)
    except email_drafts.DraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Editable draft not found")
    return result


@app.post("/admin/tenants/{slug}/email-drafts/{draft_id}/discard", dependencies=admin)
async def admin_email_draft_discard(slug: str, draft_id: int):
    _email_feature_gate()
    tenant = await _require_tenant(slug)
    result = await email_drafts.discard(tenant["id"], draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Editable draft not found")
    return result


@app.post("/admin/tenants/{slug}/email-drafts/{draft_id}/approve", dependencies=admin)
async def admin_email_draft_approve(slug: str, draft_id: int):
    _email_feature_gate()
    tenant = await _require_tenant(slug)
    try:
        result = await email_drafts.approve(tenant["id"], draft_id)
    except email_drafts.DraftError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=409, detail="Draft already handled or does not exist")
    return result



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


@app.post("/api/v1/phone/twilio/inbound")
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


@app.post("/api/v1/phone/twilio/ended")
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


@app.post("/api/v1/phone/twilio/recording")
async def twilio_phone_recording_receipt(request: Request):
    if not phone_relay.configured() or not settings.phone_recording_enabled:
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


@app.websocket("/api/v1/phone/relay")
async def twilio_phone_relay(websocket: WebSocket):
    await phone_relay.relay(websocket)


class PhoneNumberCreate(BaseModel):
    e164: str = Field(pattern=r"^\+[1-9]\d{6,14}$")


class PhoneNumberEnable(BaseModel):
    enabled: bool


@app.get("/admin/tenants/{slug}/phone-setup", dependencies=admin)
async def admin_phone_setup(slug: str):
    tenant = await _require_tenant(slug)
    row = await db.pool().fetchrow(
        "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
        tenant["id"])
    return dict(row) if row else {"status": "not_requested"}


@app.get("/admin/tenants/{slug}/phone-numbers", dependencies=admin)
async def admin_phone_numbers(slug: str):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT e164, enabled, created_at FROM phone_numbers WHERE tenant_id=$1",
        tenant["id"],
    )
    return [dict(row) for row in rows]


@app.post("/admin/tenants/{slug}/phone-numbers", dependencies=admin, status_code=201)
async def admin_phone_number_create(slug: str, body: PhoneNumberCreate):
    tenant = await _require_tenant(slug)
    row = await db.pool().fetchrow(
        "INSERT INTO phone_numbers (e164, tenant_id) VALUES ($1,$2) "
        "ON CONFLICT DO NOTHING RETURNING e164, enabled, created_at",
        body.e164, tenant["id"],
    )
    if row is None:
        raise HTTPException(status_code=409, detail="Number already registered")
    return dict(row)


@app.patch("/admin/tenants/{slug}/phone-numbers/{number}", dependencies=admin)
async def admin_phone_number_enable(slug: str, number: str, body: PhoneNumberEnable):
    tenant = await _require_tenant(slug)
    row = await db.pool().fetchrow(
        "UPDATE phone_numbers SET enabled=$3 WHERE e164=$1 AND tenant_id=$2 "
        "RETURNING e164, enabled, created_at", number, tenant["id"], body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Number not found for this business")
    return dict(row)


@app.get("/admin/tenants/{slug}/phone-calls", dependencies=admin)
async def admin_phone_call_history(slug: str):
    tenant = await _require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT call_sid, from_number, to_number, status, started_at, ended_at "
        "FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
        tenant["id"],
    )
    return [dict(row) for row in rows]

# Mailbox registration is operator-only; sending and receipt remain disabled by default.
class InboundMailbox(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    enabled: bool = False


@app.post("/admin/tenants/{slug}/inbound-mailboxes", dependencies=admin)
async def register_inbound_mailbox(slug: str, body: InboundMailbox):
    tenant = await _require_tenant(slug)
    try:
        await cloudflare_inbound.register_mailbox(tenant["id"], body.recipient, body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "enabled": body.enabled}


@app.post("/api/v1/inbound/cloudflare")
async def cloudflare_email_webhook(request: Request):
    return await cloudflare_inbound.handle(request)


@app.get("/webhooks/brevo")
async def brevo_email_webhook_status():
    """Human-friendly status for the POST-only webhook below.

    A browser click lands here, so it must not be a bare 405. This reveals nothing and
    processes nothing: Brevo is the only caller that may deliver events.
    """
    configured = bool(get_settings().brevo_webhook_secret)
    return {"ok": configured, "endpoint": "brevo webhook", "method": "POST",
            "configured": configured,
            "usage": "POST delivery events here; configure the URL in Brevo > Transactional > Settings > Webhooks"}


@app.post("/webhooks/brevo")
async def brevo_email_webhook(request: Request, token: str = ""):
    """Brevo delivery-event webhook: bounces, blocks, complaints, unsubscribes.

    Brevo posts JSON, or form-encoded with the payload in a `json` field. The shared
    secret is compared in constant time; with no secret configured the endpoint stays
    closed, so an unauthenticated caller can never suppress a customer's address.
    """
    expected = get_settings().brevo_webhook_secret
    if not expected:
        raise HTTPException(503, "Brevo webhook is not configured")
    supplied = token or request.query_params.get("token", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Invalid webhook token")
    if not flood_guard.memory_allow("brevo:webhook", "all", 120, 60):
        raise HTTPException(429, "Too many webhook calls")
    raw = await request.body()
    if len(raw) > 100_000:
        raise HTTPException(413, "Payload too large")
    try:
        if "application/json" in request.headers.get("content-type", ""):
            data = json.loads(raw or b"{}")
        else:
            form = parse_qs(raw.decode("utf-8", "replace"))
            data = json.loads((form.get("json") or ["{}"])[0])
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid payload") from None
    events = (data if isinstance(data, list) else [data])[:500]
    results = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event = dict(event)
        if not event.get("tenant_id"):
            message_id = str(event.get("message-id") or "")
            address = str(event.get("email") or "")
            row = None
            if message_id:
                row = await db.pool().fetchrow(
                    "SELECT tenant_id FROM outbox WHERE message_id=$1 ORDER BY id DESC LIMIT 1",
                    message_id)
            if row is None and address:
                row = await db.pool().fetchrow(
                    "SELECT tenant_id FROM outbox WHERE lower(to_addr)=lower($1) "
                    "ORDER BY id DESC LIMIT 1", address)
            if row is None:
                results.append({"ignored": "unknown tenant"})
                continue
            event["tenant_id"] = row["tenant_id"]
        results.append(await suppressions.record_event(event))
    return {"processed": len(results), "results": results}


class ManualSuppression(BaseModel):
    address: str = Field(max_length=320)
    reason: str = Field(default="blocked by owner", max_length=200)


@app.get("/owner/email-suppressions")
async def owner_suppressions(limit: int = 100, user: dict = Depends(owner_auth.current_user)):
    _email_feature_gate()
    return await suppressions.list_suppressions(user["tenant_id"], max(1, min(limit, 500)))


@app.post("/owner/email-suppressions", status_code=201)
async def owner_add_suppression(
    body: ManualSuppression, user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    _email_feature_gate()
    try:
        await suppressions.add(user["tenant_id"], body.address, body.reason, "owner")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"address": body.address, "suppressed": True}


@app.delete("/owner/email-suppressions/{address}")
async def owner_remove_suppression(
    address: str, user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    _email_feature_gate()
    try:
        removed = await suppressions.remove(user["tenant_id"], address)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    if not removed:
        raise HTTPException(404, "Address is not suppressed")
    return {"removed": True}


@app.get("/admin/tenants/{slug}/email-suppressions", dependencies=admin)
async def admin_suppressions(slug: str, limit: int = 200):
    tenant = await _require_tenant(slug)
    return await suppressions.list_suppressions(tenant["id"], max(1, min(limit, 500)))


# ------------------------------------------------- tenant-owner access (separate from operator)
class OwnerInvite(BaseModel):
    email: str = Field(max_length=320)
    role: Literal["viewer", "editor", "owner"] = "viewer"
    # Opt-in: email the single-use link to the invitee. Off by default so the operator can still
    # deliver it over a channel they have verified themselves.
    send_email: bool = False


class OwnerRecovery(BaseModel):
    email: str = Field(max_length=320)


class OwnerRedeem(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)


class OwnerLogin(BaseModel):
    slug: str
    email: str
    password: str


class OwnerLinkAccept(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class OwnerEmailLink(BaseModel):
    email: str = Field(max_length=320)


@app.post("/admin/tenants/{slug}/owner-invitations", dependencies=admin, status_code=201)
async def admin_invite_owner(slug: str, body: OwnerInvite):
    tenant = await _require_tenant(slug)
    try:
        token = await owner_auth.make_invite(tenant["id"], body.email, body.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    link = owner_auth.invitation_link(token)
    emailed = False
    email_error = ""
    if body.send_email:
        # The secret is in the URL fragment and redemption needs a POST with a new password, so a
        # mail scanner that pre-fetches the link cannot consume it. A failed send never fails the
        # invitation: the operator still gets the link in the response.
        try:
            name = tenant.get("name") or "your business"
            await mailer.send_email(
                owner_auth.clean_email(body.email),
                f"Your {name} Concierge is ready",
                f"Hello,\n\nYour AI front desk for {name} is ready to set up.\n\n"
                f"Open this link and you are in — there is no password to create or remember:\n{link}\n\n"
                "The link works once and expires in 24 hours. If you did not expect this "
                "message, ignore it.\n\n— Trendi Concierge",
                from_name="Trendi Concierge",
            )
            emailed = True
        except Exception as exc:  # noqa: BLE001
            email_error = type(exc).__name__
            logging.getLogger("concierge.invite").warning("invitation email not sent: %s", email_error)
    return {"invitation_token": token, "invitation_url": link, "expires_in_hours": 24,
            "emailed": emailed, "email_error": email_error}


@app.post("/admin/tenants/{slug}/owner-recovery", dependencies=admin)
async def admin_owner_recovery(slug: str, body: OwnerRecovery):
    tenant = await _require_tenant(slug)
    try:
        link = await owner_auth.owner_link(tenant["id"], body.email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"recovery_token": link["token"], "invitation_url": owner_auth.invitation_link(link["token"]),
            "purpose": link["purpose"], "role": link["role"], "expires_in_hours": 24}


@app.post("/admin/tenants/{slug}/owner-invite", dependencies=admin)
async def admin_owner_invite(slug: str, body: OwnerRecovery):
    """Send a client owner their sign-in link — queued in the outbox, so it is recorded and retried."""
    if not get_settings().email_configured:
        raise HTTPException(503, "Email is not configured on this deployment")
    try:
        result = await owner_invites.send(slug, body.email)
    except ValueError:
        raise HTTPException(404, "No such business") from None
    if not result["queued"]:
        raise HTTPException(409, "An invitation is already queued for that address")
    return result


@app.get("/owner-ui")
async def owner_ui():
    return FileResponse(
        STATIC_DIR / "owner.html", media_type="text/html",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"},
    )


STUDIO_DIR = Path("/srv/studio")


@app.get("/studio", include_in_schema=False)
@app.get("/studio/", include_in_schema=False)
async def studio_page():
    return FileResponse(STUDIO_DIR / "index.html", media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow, noai, noimageai"})


@app.get("/studio/assets/{path:path}", include_in_schema=False)
async def studio_asset(path: str):
    target = (STUDIO_DIR / "assets" / path).resolve()
    if not str(target).startswith(str((STUDIO_DIR / "assets").resolve())) or not target.is_file():
        raise HTTPException(404, "Not found")
    # Vite emits content-addressed filenames, so an asset can be cached forever: a new build
    # produces new names. Without this the browser guessed, and a tab opened before a deploy
    # asked for a chunk the deploy had already removed — the lazy-loaded page then went blank.
    return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/studio/{path:path}", include_in_schema=False)
async def studio_file(path: str):
    root = STUDIO_DIR.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return FileResponse(root / "index.html", media_type="text/html",
                            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow, noai, noimageai"})
    return FileResponse(target)


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain",
                    headers={"Cache-Control": "public, max-age=300"})


@app.get("/onboarding", include_in_schema=False)
async def onboarding_page():
    return FileResponse(
        STATIC_DIR / "onboarding.html", media_type="text/html",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"},
    )


@app.get("/owner/social/oauth/callback", include_in_schema=False)
async def owner_social_oauth_callback():
    # Public landing page only. It cannot exchange a code or authenticate anyone.
    # The original logged-in tab compares state before exchanging the code itself.
    return FileResponse(
        STATIC_DIR / "social-oauth-callback.html", media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                 "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"},
    )


@app.post("/owner/auth/redeem")
async def owner_redeem(body: OwnerRedeem):
    try:
        return await owner_auth.redeem(body.token, body.password)
    except ValueError:
        raise HTTPException(400, "Invalid invitation or password")


@app.post("/owner/auth/invite")
async def owner_accept_invite(body: OwnerLinkAccept):
    """Redeem the one-click link: sign in, no password, no account setup form."""
    try:
        return await owner_auth.accept_invite(body.token)
    except ValueError as error:
        # Say what actually happened. Collapsing every refusal into "expired or already used" sent
        # three separate investigations chasing the wrong fault.
        friendly = {
            "Link not recognised": "That link is not complete. Ask for a new one below and it will work.",
            "This link has expired": "This link has expired. Ask for a new one below.",
            "This link has already been used": "This link has already been used. Ask for a new one below.",
            "Account no longer exists": "That account no longer exists.",
        }
        raise HTTPException(400, friendly.get(str(error), str(error) or "That link did not work.")) from None


@app.post("/owner/auth/link")
async def owner_email_link(body: OwnerEmailLink, request: Request):
    """Email a one-click sign-in link.

    The answer never varies, so this cannot be used to discover which addresses have accounts.
    """
    ip = request.client.host if request.client else "unknown"
    try:
        email = owner_auth.clean_email(body.email)
    except ValueError:
        return {"ok": True}
    if not await owner_auth.allow_login_attempt(ip, "signin", email):
        raise HTTPException(429, "Too many attempts. Please try again in a few minutes.")
    for account in await owner_auth.account_emails(email):
        try:
            token = await owner_auth.make_invite(account["tenant_id"], email, account["role"], "recovery")
            await mailer.send_email(
                email,
                f"Your Concierge sign-in link — {account.get('name') or 'your business'}",
                "Hello,\n\nUse this private link to open your Concierge workspace. "
                "There is no password.\n\n"
                f"{owner_auth.invitation_link(token)}\n\n"
                "The link works once and expires in 24 hours. If you did not ask for it, "
                "you can ignore this message.\n\n— Trendi Concierge",
                from_name="Trendi Concierge",
            )
        except Exception:  # noqa: BLE001 - never reveal delivery detail to a caller
            log.exception("sign-in link could not be sent for %s", account.get("slug"))
    return {"ok": True}


@app.post("/owner/auth/login")
async def owner_login(body: OwnerLogin, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not await owner_auth.allow_login_attempt(ip, body.slug, body.email):
        raise HTTPException(429, "Too many login attempts")
    try:
        token = await owner_auth.login_for_tenant(body.slug, body.email, body.password)
    except ValueError:
        token = None
    if token is None:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": token, "token_type": "bearer", "expires_in": 43200}


COUNTRY_LOCALE = {
    "FR": "fr-FR", "BE": "fr-FR", "CA": "fr-FR", "CH": "fr-FR",
    "ES": "es-ES", "MX": "es-ES", "AR": "es-ES", "CO": "es-ES", "CL": "es-ES",
    "DE": "de-DE", "AT": "de-DE",
    "BR": "pt-BR", "PT": "pt-BR",
    "CN": "zh-CN", "TW": "zh-CN", "HK": "zh-CN", "SG": "zh-CN",
    "JP": "ja-JP", "KR": "ko-KR",
    "SA": "ar-SA", "AE": "ar-SA", "EG": "ar-SA", "QA": "ar-SA",
    "NL": "nl-NL",
    "IT": "it-IT",
    "PL": "pl-PL",
}


@app.get("/owner/locale")
async def owner_locale(request: Request):
    country = (request.headers.get("cf-ipcountry") or "").upper()
    return {"country": country, "locale": COUNTRY_LOCALE.get(country, "en"),
            "supported": ["en", "fr-FR", "es-ES", "de-DE", "pt-BR", "zh-CN", "ja-JP", "ko-KR", "ar-SA", "nl-NL", "it-IT", "pl-PL"]}


@app.get("/owner/me")
async def owner_me(user: dict = Depends(owner_auth.current_user)):
    return {"email": user["email"], "role": user["role"], "tenant": user["slug"]}


from . import webpush  # noqa: E402 - Web Push for owner alerts (installed portal)


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscribe(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000)
    keys: PushKeys
    user_agent: str = Field(default="", max_length=300)


class PushEndpoint(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000)


@app.get("/owner/sw.js", include_in_schema=False)
async def owner_service_worker():
    """The owner page's alert worker. Served under /owner/ (the only prefix the public proxy forwards)
    and allowed to control /owner-ui, which a worker at this path could not otherwise do."""
    return FileResponse(STATIC_DIR / "owner-sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
                                 "Service-Worker-Allowed": "/owner-ui"})


from fastapi.exception_handlers import request_validation_exception_handler  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

_FIELD_LABELS = {"password": "Password", "token": "Invitation link", "email": "Email address",
                 "slug": "Business ID", "endpoint": "Device address"}


def plain_validation_message(errors) -> str:
    """Turn FastAPI's list of validation errors into one sentence a person can act on.

    The portals show `detail` as text. FastAPI's default is a list of objects, which a page prints as
    "[object Object]" (seen on the first invite, 2026-11-13). It also echoes the submitted value, which for the
    password box is the password itself. This never repeats what was typed.
    """
    parts = []
    for error in list(errors)[:3]:
        location = [str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path")]
        field = location[-1] if location else "value"
        label = _FIELD_LABELS.get(field, field.replace("_", " ").capitalize())
        kind = error.get("type", "")
        context = error.get("ctx") or {}
        if field == "token" and kind in ("string_too_short", "string_too_long", "missing"):
            parts.append("The invitation link looks incomplete. Open it again from your email.")
        elif kind == "string_too_short":
            parts.append(f"{label} must be at least {context.get('min_length')} characters.")
        elif kind == "string_too_long":
            parts.append(f"{label} must be at most {context.get('max_length')} characters.")
        elif kind == "missing":
            parts.append(f"{label} is required.")
        elif kind == "value_error":
            # A message the application wrote for the person ("Enter a public HTTPS website address"); it never
            # contains what they typed, so it is safe to show as it is.
            text = str(error.get("msg", "")).removeprefix("Value error, ").strip()
            parts.append((text if text.endswith((".", "!", "?")) else text + ".") if text else f"{label} is not valid.")
        else:
            parts.append(f"{label} is not valid.")
    return " ".join(dict.fromkeys(parts)) or "Some details are not valid."


@app.exception_handler(RequestValidationError)
async def owner_validation_errors(request, exc):
    if request.url.path.startswith("/owner/"):
        return JSONResponse({"detail": plain_validation_message(exc.errors())}, status_code=422,
                            headers={"Cache-Control": "no-store"})
    return await request_validation_exception_handler(request, exc)


@app.get("/owner/push/key")
async def owner_push_key(user: dict = Depends(owner_auth.current_user)):
    if not webpush.configured():
        raise HTTPException(503, "Phone alerts are not set up on this server yet")
    return {"public_key": settings.vapid_public_key}


@app.post("/owner/push/subscribe", status_code=201)
async def owner_push_subscribe(body: PushSubscribe, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not webpush.allowed_endpoint(body.endpoint):
        raise HTTPException(400, "That device's push service is not supported")
    await webpush.save(user["tenant_id"], body.endpoint, body.keys.p256dh, body.keys.auth, body.user_agent)
    return {"subscribed": True}


@app.post("/owner/push/unsubscribe")
async def owner_push_unsubscribe(body: PushEndpoint, user: dict = Depends(owner_auth.current_user)):
    await webpush.remove(user["tenant_id"], body.endpoint)
    return {"subscribed": False}


@app.post("/owner/push/test", status_code=202)
async def owner_push_test(body: PushEndpoint, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await webpush.send_test(user["tenant_id"], body.endpoint)


@app.get("/owner/channel-health")
async def owner_channel_health(user: dict = Depends(owner_auth.current_user)):
    """Plain status of email alerts, the SMS phone and voice calls for this business."""
    return await channel_health.channel_report(user["tenant_id"])


@app.post("/owner/alerts/test", status_code=202)
async def owner_test_alert(user: dict = Depends(owner_auth.current_user)):
    """Send a test alert to the owner's own email and mobile so they can confirm it arrives."""
    owner_auth.require_role(user, "owner")
    tenant = await _require_tenant(user["slug"])
    return await channel_health.send_test_alert(tenant)


@app.post("/admin/tenants/{slug}/test-alert", dependencies=admin, status_code=202)
async def admin_test_alert(slug: str):
    tenant = await _require_tenant(slug)
    result = await channel_health.send_test_alert(tenant)
    return {**result, "go_live_blockers": await channel_health.go_live_blockers(tenant)}


@app.get("/owner/crm")
async def owner_crm(user: dict = Depends(owner_auth.current_user)):
    tenant = await tenants.ensure_calendar_token(await _require_tenant(user["slug"]))
    leads, appointments, todos = await asyncio.gather(
        admin_leads(user["slug"]), admin_appointments(user["slug"]),
        tasks.list_tasks(user["tenant_id"], "all"))
    return {"leads": leads, "appointments": appointments, "tasks": todos,
            "calendar_url": _origin_of(settings.owner_portal_url) + "/api/v1/calendar/" + tenant["calendar_token"] + ".ics"}


@app.get("/owner/crm/leads/{lead_id}/transcript")
async def owner_crm_transcript(lead_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    exists = await db.pool().fetchval(
        "SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2", user["tenant_id"], lead_id)
    if not exists:
        raise HTTPException(404, "Enquiry not found")
    rows = await db.pool().fetch(
        "SELECT m.role,m.content,m.created_at FROM leads l "
        "JOIN conversations c ON c.id=l.conversation_id AND c.tenant_id=l.tenant_id "
        "JOIN messages m ON m.conversation_id=c.id "
        "WHERE l.tenant_id=$1 AND l.id=$2 AND m.role IN ('user','assistant') "
        "ORDER BY m.id LIMIT 1000", user["tenant_id"], lead_id)
    return [dict(row) for row in rows] if rows else [
        {'role': 'user', 'content': row['original_text'], 'created_at': row['created_at']}
        for row in await db.pool().fetch('SELECT original_text,created_at FROM enquiry_sources WHERE tenant_id=$1 AND lead_id=$2 ORDER BY created_at', user['tenant_id'], lead_id)]


@app.get("/owner/crm/leads/{lead_id}/recordings")
async def owner_crm_recordings(lead_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    return await voice_records.recordings_for_lead(user["tenant_id"], lead_id)


@app.get("/owner/voice-recordings/{session_id}")
async def owner_voice_recording(session_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    row = await voice_records.audio_for_owner(user["tenant_id"], session_id)
    return private_audio_response(row, "concierge-recording." + row["mime_type"].split("/")[1])


@app.post("/owner/voice-recordings/{session_id}/share")
async def owner_share_voice_recording(session_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    token = await voice_records.share(user["tenant_id"], session_id)
    return {"url": settings.public_base_url.rstrip("/")+"/api/v1/voice/recordings/shared/"+token, "expires_in_hours": 24}


class VoiceCopyRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=254)
    channel: Literal["sms", "email"]
    content: Literal["text", "recording"]
    request_id: uuid.UUID
    session_id: uuid.UUID | None = None


@app.post("/owner/crm/leads/{lead_id}/deliver")
async def owner_deliver_voice_copy(lead_id: uuid.UUID, body: VoiceCopyRequest, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user["tenant_id"])
    return await voice_records.deliver(tenant, lead_id, **body.model_dump())


class OwnerTaskCreate(TaskCreate):
    pass


@app.get("/owner/tasks")
async def owner_tasks(status: Literal["open", "done", "all"] = "open",
                      user: dict = Depends(owner_auth.current_user)):
    """The owner's own to-do list. Tasks existed but only admins could reach them."""
    owner_auth.require_role(user, "viewer")
    return await tasks.list_tasks(user["tenant_id"], status)


@app.post("/owner/tasks", status_code=201)
async def owner_task_create(body: OwnerTaskCreate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if body.lead_id:
        try:
            found = await db.pool().fetchval(
                "SELECT 1 FROM leads WHERE id=$1::uuid AND tenant_id=$2", body.lead_id, user["tenant_id"])
        except Exception:
            raise HTTPException(400, "Invalid lead id")
        if not found:
            raise HTTPException(404, "Unknown lead")
    try:
        return await tasks.create(user["tenant_id"], body.title, body.notes, body.due_at,
                                  lead_id=body.lead_id)
    except tasks.TaskError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/owner/tasks/{task_id}")
async def owner_task_update(task_id: int, body: TaskUpdate,
                            user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await db.pool().fetchval("SELECT 1 FROM tasks WHERE id=$1 AND tenant_id=$2",
                                    task_id, user["tenant_id"]):
        raise HTTPException(404, "Unknown to-do")
    try:
        row = await tasks.update(task_id, body.model_dump(exclude_unset=True))
    except tasks.TaskError as exc:
        raise HTTPException(400, str(exc))
    if row is None:
        raise HTTPException(404, "Unknown to-do")
    return row


@app.delete("/owner/tasks/{task_id}")
async def owner_task_delete(task_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await db.pool().fetchval("SELECT 1 FROM tasks WHERE id=$1 AND tenant_id=$2",
                                    task_id, user["tenant_id"]):
        raise HTTPException(404, "Unknown to-do")
    return {"deleted": await tasks.delete(task_id)}



class CompanyBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    parent_id: str | None = None


class Assignee(BaseModel):
    user_id: str | None = None


async def _require_member(tenant_id, user_id: str) -> str | None:
    """An assignee must be someone who can actually get in to this workspace."""
    if user_id in (None, "", "unassigned"):
        return None
    try:
        found = await db.pool().fetchval(
            "SELECT id FROM tenant_users WHERE id=$1::uuid AND tenant_id=$2 AND active", user_id, tenant_id)
    except Exception:
        raise HTTPException(400, "Invalid team member id")
    if not found:
        raise HTTPException(404, "That person is not on your team")
    return str(found)


async def _require_company(tenant_id, company_id: str) -> str:
    try:
        found = await db.pool().fetchval(
            "SELECT id FROM companies WHERE id=$1::uuid AND tenant_id=$2", company_id, tenant_id)
    except Exception:
        raise HTTPException(400, "Invalid company id")
    if not found:
        raise HTTPException(404, "Unknown company")
    return str(found)


@app.get("/owner/companies")
async def owner_companies(user: dict = Depends(owner_auth.current_user)):
    """Companies, each with the people and open value attached to it."""
    rows = await db.pool().fetch(
        """
        SELECT c.id, c.name, c.domain, c.notes, c.parent_id,
               (SELECT count(*) FROM customer_cases k WHERE k.company_id = c.id) AS contacts,
               (SELECT count(*) FROM leads l JOIN customer_cases k ON l.case_id = k.id
                 WHERE k.company_id = c.id AND l.status IN ('new','contacted','booked')) AS open_deals,
               (SELECT coalesce(sum(l.value_cents),0) FROM leads l JOIN customer_cases k ON l.case_id = k.id
                 WHERE k.company_id = c.id AND l.status IN ('new','contacted','booked')) AS open_value_cents
          FROM companies c WHERE c.tenant_id = $1 ORDER BY c.name
        """, user["tenant_id"])
    return [dict(row) for row in rows]


@app.post("/owner/companies", status_code=201)
async def owner_company_create(body: CompanyBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        row = await db.pool().fetchrow(
            "INSERT INTO companies (tenant_id, name, domain, notes) VALUES ($1,$2,$3,$4) RETURNING *",
            user["tenant_id"], body.name.strip(), body.domain.strip(), body.notes.strip())
    except Exception:
        raise HTTPException(409, "You already have a company with that name")
    return dict(row)


@app.patch("/owner/companies/{company_id}")
async def owner_company_update(company_id: str, body: CompanyUpdate,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(400, "Nothing to update")
    if "parent_id" in fields:
        fields["parent_id"] = await _require_company(user["tenant_id"], fields["parent_id"]) if fields["parent_id"] else None
    parts = [f"{col} = ${i}" for i, col in enumerate(fields, start=3)]
    row = await db.pool().fetchrow(
        f"UPDATE companies SET {', '.join(parts)}, updated_at = now() "
        "WHERE id = $1::uuid AND tenant_id = $2 RETURNING *",
        company_id, user["tenant_id"], *fields.values())
    if row is None:
        raise HTTPException(404, "Unknown company")
    return dict(row)


@app.delete("/owner/companies/{company_id}")
async def owner_company_delete(company_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    gone = await db.pool().fetchval(
        "DELETE FROM companies WHERE id=$1::uuid AND tenant_id=$2 RETURNING id",
        company_id, user["tenant_id"])
    if gone is None:
        raise HTTPException(404, "Unknown company")
    return {"deleted": True}


@app.put("/owner/contacts/{case_key}/company")
async def owner_contact_company(case_key: str, body: dict,
                                user: dict = Depends(owner_auth.current_user)):
    """Put a person inside a company, or take them out of one."""
    owner_auth.require_role(user, "editor")
    company_id = await _require_company(user["tenant_id"], body.get("company_id")) if body.get("company_id") else None
    row = await db.pool().fetchrow(
        "UPDATE customer_cases SET company_id=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key=$2 RETURNING case_key",
        user["tenant_id"], case_key.strip().lower()[:200], company_id)
    if row is None:
        raise HTTPException(404, "Unknown contact")
    return {"case_key": row["case_key"], "company_id": company_id}


@app.put("/owner/contacts/{case_key}/assignee")
async def owner_contact_assignee(case_key: str, body: Assignee,
                                 user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    row = await db.pool().fetchrow(
        "UPDATE customer_cases SET assigned_to=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key=$2 RETURNING case_key",
        user["tenant_id"], case_key.strip().lower()[:200], assignee)
    if row is None:
        raise HTTPException(404, "Unknown contact")
    return {"case_key": row["case_key"], "assigned_to": assignee}


@app.put("/owner/crm/leads/{lead_id}/assignee")
async def owner_lead_assignee(lead_id: str, body: Assignee,
                              user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    try:
        row = await db.pool().fetchrow(
            "UPDATE leads SET assigned_to=$3, updated_at=now() "
            "WHERE id=$1::uuid AND tenant_id=$2 RETURNING id, assigned_to",
            lead_id, user["tenant_id"], assignee)
    except Exception:
        raise HTTPException(404, "Enquiry not found")
    if row is None:
        raise HTTPException(404, "Enquiry not found")
    return {"id": str(row["id"]),
            "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None}


class BulkAssign(BaseModel):
    case_keys: list[str] = Field(min_length=1, max_length=200)
    user_id: str | None = None


@app.post("/owner/contacts/bulk-assign")
async def owner_contacts_bulk_assign(body: BulkAssign, user: dict = Depends(owner_auth.current_user)):
    """Give a batch of people the same owner, or take the owner off all of them.

    A team that cannot reassign twenty contacts at once will not use ownership at all.
    """
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    keys = [key.strip().lower()[:200] for key in body.case_keys if key.strip()]
    updated = await db.pool().fetch(
        "UPDATE customer_cases SET assigned_to=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key = ANY($2::text[]) RETURNING case_key",
        user["tenant_id"], keys, assignee)
    return {"updated": len(updated), "assigned_to": assignee, "case_keys": [r["case_key"] for r in updated]}


@app.get("/owner/reports/export.csv")
async def owner_reports_export(days: int = 30, user: dict = Depends(owner_auth.current_user)):
    """What a business needs to hand to an accountant or a spreadsheet.

    The reports page could show the numbers but not let them leave, and it had no lost-reason or
    source breakdown at all -- the two questions every owner asks first.
    """
    owner_auth.require_role(user, "viewer")
    rows = await db.pool().fetch(
        """
        SELECT l.status, l.channel, l.lost_reason, count(*) AS enquiries,
               coalesce(sum(l.value_cents),0) AS value_cents
          FROM leads l
         WHERE l.tenant_id = $1 AND l.created_at > now() - make_interval(days => $2)
         GROUP BY l.status, l.channel, l.lost_reason
         ORDER BY l.status, enquiries DESC
        """, user["tenant_id"], max(1, min(days, 365)))
    quotes = await db.pool().fetch(
        """
        SELECT status, count(*) AS quotes, coalesce(sum(total_cents),0) AS total_cents
          FROM quotations WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)
         GROUP BY status ORDER BY status
        """, user["tenant_id"], max(1, min(days, 365)))
    lines = ["section,stage_or_status,channel,lost_reason,count,value_cents"]
    for row in rows:
        lines.append(_csv_row("enquiries", row["status"], row["channel"], row["lost_reason"],
                              row["enquiries"], row["value_cents"]))
    for row in quotes:
        lines.append(_csv_row("quotes", row["status"], "", "", row["quotes"], row["total_cents"]))
    return Response("\n".join(lines) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=concierge-report.csv"})


def _csv_row(*cells) -> str:
    out = []
    for cell in cells:
        text = "" if cell is None else str(cell)
        out.append('"' + text.replace('"', '""') + '"' if any(ch in text for ch in ',"\n') else text)
    return ",".join(out)


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=8000)


@app.get("/owner/email-templates")
async def owner_templates(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, name, subject, body, updated_at FROM email_templates "
        "WHERE tenant_id=$1 ORDER BY name", user["tenant_id"])
    return [dict(row) for row in rows]


@app.post("/owner/email-templates", status_code=201)
async def owner_template_create(body: TemplateBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        row = await db.pool().fetchrow(
            "INSERT INTO email_templates (tenant_id, name, subject, body) VALUES ($1,$2,$3,$4) RETURNING *",
            user["tenant_id"], body.name.strip(), body.subject.strip(), body.body.rstrip())
    except Exception:
        raise HTTPException(409, "You already have a saved reply with that name")
    return dict(row)


@app.patch("/owner/email-templates/{template_id}")
async def owner_template_update(template_id: str, body: TemplateBody,
                                user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        row = await db.pool().fetchrow(
            "UPDATE email_templates SET name=$3, subject=$4, body=$5, updated_at=now() "
            "WHERE id=$1::uuid AND tenant_id=$2 RETURNING *",
            template_id, user["tenant_id"], body.name.strip(), body.subject.strip(), body.body.rstrip())
    except Exception:
        raise HTTPException(409, "You already have a saved reply with that name")
    if row is None:
        raise HTTPException(404, "Unknown saved reply")
    return dict(row)


@app.delete("/owner/email-templates/{template_id}")
async def owner_template_delete(template_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    gone = await db.pool().fetchval(
        "DELETE FROM email_templates WHERE id=$1::uuid AND tenant_id=$2 RETURNING id",
        template_id, user["tenant_id"])
    if gone is None:
        raise HTTPException(404, "Unknown saved reply")
    return {"deleted": True}

@app.patch("/owner/crm/leads/{lead_id}")
async def owner_crm_update(lead_id: str, body: LeadUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        exists = await db.pool().fetchval("SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2::uuid",
                                         user["tenant_id"], lead_id)
    except Exception:
        raise HTTPException(404, "Enquiry not found")
    if not exists:
        raise HTTPException(404, "Enquiry not found")
    updated = await admin_update_lead(lead_id, body)
    if body.status:
        await db.pool().execute(
            "UPDATE lead_events SET actor=$2 WHERE lead_id=$1::uuid AND actor='' "
            "AND id = (SELECT max(id) FROM lead_events WHERE lead_id=$1::uuid)",
            lead_id, user.get("email") or "")
    return updated


class CaseTakeoverRequest(BaseModel):
    paused: bool


@app.get("/owner/crm/leads/{lead_id}/case")
async def owner_lead_case(lead_id: str, user: dict = Depends(owner_auth.current_user)):
    """The customer's unified case: every channel, one history, plus the response deadline.

    Scoped to the caller's tenant by joining through `leads`, so a lead id from another business
    resolves to nothing rather than to their data.
    """
    tenant = await tenants.get_by_id(user["tenant_id"])
    lead = await db.pool().fetchrow(
        "SELECT id, case_id, name, phone, email, message, status, created_at, channel "
        "FROM leads WHERE tenant_id=$1 AND id=$2::uuid",
        user["tenant_id"], lead_id)
    if not lead:
        raise HTTPException(404, "Enquiry not found")

    events = []
    case = None
    if lead["case_id"]:
        case = await db.pool().fetchrow(
            "SELECT case_key, primary_phone, primary_email, automation_paused, takeover_at "
            "FROM customer_cases WHERE tenant_id=$1 AND id=$2",
            user["tenant_id"], lead["case_id"])
        if case:
            events = await casetimeline.timeline(
                user["tenant_id"], case["case_key"], limit=200)

    return {
        "lead_id": str(lead["id"]),
        "case_key": case["case_key"] if case else None,
        "automation_paused": bool(case["automation_paused"]) if case else False,
        "takeover_at": case["takeover_at"].isoformat() if case and case["takeover_at"] else None,
        "channels_seen": sorted({e["channel"] for e in events}),
        "event_count": len(events),
        "events": [
            {
                "channel": e["channel"],
                "direction": e["direction"],
                "body": e["body"],
                "occurred_at": e["occurred_at"].isoformat() if e["occurred_at"] else None,
                "answered_at": e["answered_at"].isoformat() if e["answered_at"] else None,
            }
            for e in events
        ],
        "deadline": hermes_orchestrator.deadline_state(
            tenant or {}, {"created_at": lead["created_at"]}),
    }


class ContactTakeover(BaseModel):
    paused: bool
    reason: str = ""


class LiveTakeover(BaseModel):
    reason: str = ""


class LiveSupervise(BaseModel):
    """How an owner wants to join a live call: hear it, coach it, or join it."""
    mode: Literal["listen", "whisper", "join"] = "listen"


@app.get("/owner/live-calls")
async def owner_live_calls(user: dict = Depends(owner_auth.current_user)):
    """Calls happening right now, with the conversation so far — the Switchboard, narrowed.

    Each call says which engine it is on and which controls are real for it (see live_calls.py).
    On the Asterisk line (`ast:`) the PBX owns the media, so take-over, listen-in and whisper are
    genuine audio actions; on Grok SIP calls (`sip:`) take-over stops the AI and alerts the owner
    to ring back, because that provider exposes no transfer or audio join.
    """
    return {"calls": await live_calls.active(user["tenant_id"]),
            "media_control": call_control.enabled()}


@app.get("/owner/live-calls/{call_sid}")
async def owner_live_call(call_sid: str, user: dict = Depends(owner_auth.current_user)):
    found = await live_calls.one(user["tenant_id"], call_sid)
    if not found:
        raise HTTPException(404, "Call not found")
    return found


@app.post("/owner/live-calls/{call_sid}/supervise")
async def owner_live_supervise(
    call_sid: str, body: LiveSupervise, user: dict = Depends(owner_auth.current_user)
):
    """Ring the owner's phone and join it to the live call: listen, whisper, or join.

    The media server does the work (Asterisk `ChanSpy` on the caller's channel through the same
    carrier trunk). Nothing is written to the caller's transcript — this is the owner listening.
    """
    tenant = await _require_tenant(user["slug"])
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


@app.post("/owner/live-calls/{call_sid}/supervise/stop")
async def owner_live_supervise_stop(
    call_sid: str, user: dict = Depends(owner_auth.current_user)
):
    """End every supervision leg on this call (the owner hanging up their own listening).

    The audit row closes with who stopped it; the caller and the assistant are untouched.
    """
    tenant = await _require_tenant(user["slug"])
    row = await db.pool().fetchrow(
        "SELECT * FROM phone_calls WHERE tenant_id = $1 AND call_sid = $2",
        user["tenant_id"], call_sid)
    if not row:
        raise HTTPException(404, "Call not found")
    by = user.get("email") or user.get("role") or "owner"
    result = await live_calls.stop_supervision(tenant, call_sid, by=str(by))
    return {"ok": True, **result}


@app.get("/owner/supervision")
async def owner_supervision(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """The supervision audit trail: who listened to which call, in what mode, and for how long.

    Legs are closed against the PBX before they are read, so a supervisor who simply hung up
    their phone cannot leave a session showing as still listening.
    """
    await live_calls.reconcile_supervision(user["tenant_id"])
    return {"sessions": await supervision.recent(user["tenant_id"], limit),
            "media_control": call_control.enabled()}


@app.post("/owner/live-calls/{call_sid}/takeover")
async def owner_live_takeover(
    call_sid: str, body: LiveTakeover, user: dict = Depends(owner_auth.current_user)
):
    tenant = await _require_tenant(user["slug"])
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


class PaymentSettings(BaseModel):
    instructions: str = ""
    url: str = ""


class QuotePaymentAction(BaseModel):
    action: str = "confirm"       # confirm | waive
    reference: str = ""


@app.get("/owner/revenue")
async def owner_revenue(days: int = 30, user: dict = Depends(owner_auth.current_user)):
    """What the AI brought in, in money, with the previous period beside it."""
    return await revenue.report(user["tenant_id"], days)


class BusinessDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    gst_number: str = Field(default='', max_length=32)
    nzbn: str = Field(default='', max_length=32)
    business_address: str = Field(default='', max_length=500)
    business_phone: str = Field(default='', max_length=64)
    quote_terms: str = Field(default='', max_length=4000)
    quote_valid_days: int = Field(default=30, ge=1, le=365)
    allow_deposit: bool = True
    deposit_percent: int = Field(default=50, ge=0, le=100)
    invoice_payment_terms_days: int = Field(default=7, ge=0, le=120)


# ------------------------------------------- installing the chat on their site


class InstallRequest(BaseModel):
    website: str = Field(default="", max_length=300)
    platform: str = Field(default="unsure", max_length=30)
    contact_name: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=1000)


@app.post("/owner/install-request")
async def owner_install_request(body: InstallRequest, user: dict = Depends(owner_auth.current_user)):
    """The customer asks us to put the chat on their site. No code, no third party."""
    return await install_requests.create(
        user["tenant_id"], body.website, body.platform, body.contact_name, body.contact_phone,
        body.note)


@app.get("/owner/install-requests")
async def owner_install_requests(user: dict = Depends(owner_auth.current_user)):
    return await install_requests.for_tenant(user["tenant_id"])


@app.get("/admin/install-requests", dependencies=admin)
async def admin_install_requests(status: str = ""):
    return await install_requests.list_all(status)


@app.post("/admin/install-requests/{request_id}/status", dependencies=admin)
async def admin_install_request_status(request_id: str, status: str = "done"):
    try:
        return await install_requests.set_status(request_id, status)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@app.get("/owner/business")
async def owner_business(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        'SELECT name,gst_number,nzbn,business_address,business_phone,quote_terms,quote_valid_days,'
        'allow_deposit,deposit_percent,invoice_payment_terms_days '
        'FROM tenants WHERE id=$1', user["tenant_id"])
    return dict(row)


@app.put("/owner/business")
async def owner_business_update(body: BusinessDetails, user: dict = Depends(owner_auth.current_user)):
    """The details every quotation prints: who issued it, their GST number, and how long it holds."""
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        'UPDATE tenants SET name=$2, gst_number=$3, nzbn=$4, business_address=$5, business_phone=$6, '
        'quote_terms=$7, quote_valid_days=$8, allow_deposit=$9, deposit_percent=$10, '
        'invoice_payment_terms_days=$11 WHERE id=$1 '
        'RETURNING name,gst_number,nzbn,business_address,business_phone,quote_terms,quote_valid_days,'
        'allow_deposit,deposit_percent,invoice_payment_terms_days',
        user["tenant_id"], body.name.strip(), body.gst_number.strip(), body.nzbn.strip(),
        body.business_address.strip(), body.business_phone.strip(), body.quote_terms.strip(),
        body.quote_valid_days, body.allow_deposit, body.deposit_percent,
        body.invoice_payment_terms_days)
    return dict(row)


@app.get("/owner/payment-settings")
async def owner_payment_settings(user: dict = Depends(owner_auth.current_user)):
    """How this business asks to be paid, and what money is in flight. Processor-free by design."""
    tenant = await db.pool().fetchrow(
        "SELECT payment_instructions, payment_url FROM tenants WHERE id=$1", user["tenant_id"])
    return {
        "instructions": (tenant["payment_instructions"] if tenant else "") or "",
        "url": (tenant["payment_url"] if tenant else "") or "",
        "summary": await quote_payments.summary(user["tenant_id"]),
    }


@app.put("/owner/payment-settings")
async def owner_set_payment_settings(
    body: PaymentSettings, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    url = body.url.strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "The payment link must start with http:// or https://")
    await db.pool().execute(
        "UPDATE tenants SET payment_instructions=$2, payment_url=$3 WHERE id=$1",
        user["tenant_id"], body.instructions.strip()[:2000], url[:500])
    return {"ok": True}


@app.post("/owner/crm/quotations/{quote_id}/payment")
async def owner_quote_payment(
    quote_id: str, body: QuotePaymentAction, user: dict = Depends(owner_auth.current_user)
):
    """Confirm the money arrived (the only path to paid) or waive it."""
    owner_auth.require_role(user, "owner")
    if body.action not in ("confirm", "waive"):
        raise HTTPException(422, "action must be confirm or waive")
    row = await db.pool().fetchrow(
        "SELECT * FROM quotations WHERE tenant_id=$1 AND id=$2::uuid",
        user["tenant_id"], quote_id)
    if not row:
        raise HTTPException(404, "Quotation not found")
    quote = quotations.view(row)
    result = await quote_payments.confirm(
        quote, by=user.get("email") or "owner", waive=body.action == "waive")
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason") or "That quotation cannot be updated")
    return result


@app.get("/owner/call-insights")
async def owner_call_insights(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """What happened on recent calls: summary, outcome, how the caller felt, the next step."""
    rows = await call_insights.recent(user["tenant_id"], limit)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    return {"insights": rows, "counts_by_outcome": counts, "outcomes": list(call_insights.OUTCOMES)}


@app.get("/owner/contacts")
async def owner_contacts(
    limit: int = 50, q: str = "", user: dict = Depends(owner_auth.current_user)
):
    """One row per customer, not per enquiry — the list behind the unified timeline.

    Covers the competitor-gap item C: GoHighLevel's real moat is a single Conversations inbox, and
    Concierge already merges the channels at the case level (casetimeline). This exposes it.
    """
    rows = await db.pool().fetch(
        """
        SELECT c.case_key, c.display_name, c.company, c.primary_phone, c.primary_email,
               c.assigned_to, c.company_id,
               (SELECT u.email FROM tenant_users u WHERE u.id = c.assigned_to) AS assignee_email,
               (SELECT co.name FROM companies co WHERE co.id = c.company_id) AS company_name,
               c.automation_paused, c.takeover_at, c.updated_at,
               (SELECT count(*) FROM case_events e WHERE e.case_id = c.id) AS event_count,
               (SELECT string_agg(DISTINCT e.channel, ',') FROM case_events e
                 WHERE e.case_id = c.id) AS channels,
               (SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id = c.id) AS last_at
        FROM customer_cases c
        WHERE c.tenant_id = $1
          AND ($2 = '' OR c.display_name ILIKE '%' || $2 || '%'
               OR c.primary_phone LIKE '%' || $2 || '%'
               OR c.primary_email ILIKE '%' || $2 || '%')
        -- Postgres will not accept a select alias inside an expression here: ORDER BY last_at
        -- works, ORDER BY COALESCE(last_at, ...) does not, and it failed at prepare time with
        -- "column last_at does not exist". Repeat the subquery instead; it is one index hit.
        ORDER BY COALESCE((SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id = c.id),
                          c.updated_at) DESC
        LIMIT $3
        """,
        user["tenant_id"], q.strip(), max(1, min(limit, 200)),
    )
    contacts = []
    for row in rows:
        item = dict(row)
        channels = [c for c in (item.pop("channels", "") or "").split(",") if c]
        item["channels"] = sorted(channels)
        item["label"] = casetimeline.contact_label(item)
        item["last_at"] = item["last_at"].isoformat() if item.get("last_at") else None
        item["updated_at"] = item["updated_at"].isoformat() if item.get("updated_at") else None
        item["takeover_at"] = item["takeover_at"].isoformat() if item.get("takeover_at") else None
        contacts.append(item)
    return {"contacts": contacts, "count": len(contacts)}


class AddressIn(BaseModel):
    kind: Literal["phone", "email"]
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=60)


class ImportIn(BaseModel):
    format: Literal["csv", "json"] = "csv"
    data: str = Field(default="", max_length=2_000_000)
    contacts: list[dict] = Field(default_factory=list)


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    secret: str = Field(min_length=16, max_length=200)


async def _case_id_for(user: dict, case_key: str):
    row = await db.pool().fetchrow(
        "SELECT id FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
        user["tenant_id"], case_key)
    if not row:
        raise HTTPException(404, "Customer not found")
    return row["id"]


@app.get("/owner/contacts/{case_key}/addresses")
async def owner_addresses(case_key: str, user: dict = Depends(owner_auth.current_user)):
    case_id = await _case_id_for(user, case_key)
    return {"addresses": await casetimeline.list_addresses(user["tenant_id"], case_id)}


@app.post("/owner/contacts/{case_key}/addresses", status_code=201)
async def owner_add_address(case_key: str, body: AddressIn,
                            user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    case_id = await _case_id_for(user, case_key)
    try:
        tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", user["tenant_id"])
        address = await casetimeline.add_address(
            user["tenant_id"], case_id, kind=body.kind, value=body.value, label=body.label,
            default_cc=casetimeline.tenant_country_code(dict(tenant) if tenant else None))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return address


@app.delete("/owner/contacts/{case_key}/addresses/{address_id}")
async def owner_remove_address(case_key: str, address_id: int,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    case_id = await _case_id_for(user, case_key)
    try:
        removed = await casetimeline.remove_address(user["tenant_id"], case_id, address_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not removed:
        raise HTTPException(404, "Address not found")
    return {"removed": True}


@app.get("/owner/export/contacts")
async def owner_export_contacts(format: Literal["json", "csv"] = "json",
                                user: dict = Depends(owner_auth.current_user)):
    """Take your customer list with you: JSON for a CRM importer, CSV for a spreadsheet.

    This is the promise that nobody is locked in. It is a plain GET so it also works from a
    browser address bar, with the session cookie.
    """
    contacts = await portability.export_contacts(user["tenant_id"])
    if format == "csv":
        return Response(content=portability.to_csv(contacts), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="customers.csv"'})
    return {"contacts": contacts, "count": len(contacts)}


@app.post("/owner/import/contacts")
async def owner_import_contacts(body: ImportIn, user: dict = Depends(owner_auth.current_user)):
    """Bring your existing customer list in. Safe to run twice: matches on any known address."""
    owner_auth.require_role(user, "editor")
    if body.format == "csv":
        rows = portability.parse_import(body.data)
    else:
        rows = [{"name": c.get("name") or c.get("display_name") or "",
                 "phone": c.get("phone") or c.get("primary_phone") or "",
                 "email": c.get("email") or c.get("primary_email") or "",
                 "extra": c.get("extra") or ""} for c in body.contacts]
    if not rows:
        raise HTTPException(400, "Nothing to import: no rows found")
    tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", user["tenant_id"])
    result = await portability.import_contacts(
        user["tenant_id"], rows,
        default_cc=casetimeline.tenant_country_code(dict(tenant) if tenant else None))
    return result


@app.get("/owner/webhooks")
async def owner_get_webhook(user: dict = Depends(owner_auth.current_user)):
    """Where new customers are pushed, if this business runs its own CRM."""
    return {"webhook": await portability.get_webhook(user["tenant_id"])}


@app.post("/owner/webhooks")
async def owner_set_webhook(body: WebhookIn, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not body.url.startswith("https://"):
        raise HTTPException(400, "Use an https address for your CRM endpoint")
    return await portability.set_webhook(user["tenant_id"], body.url.strip(), body.secret)


@app.delete("/owner/webhooks")
async def owner_delete_webhook(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    await portability.delete_webhook(user["tenant_id"])
    return {"removed": True}


@app.post("/owner/webhooks/deliver")
async def owner_deliver_webhook(user: dict = Depends(owner_auth.current_user)):
    """Retry anything queued, for when their endpoint was down."""
    owner_auth.require_role(user, "owner")
    return await portability.deliver_pending(user["tenant_id"])


@app.get("/owner/contacts/{case_key}/timeline")
async def owner_contact_timeline(
    case_key: str, limit: int = 200, user: dict = Depends(owner_auth.current_user)
):
    """Everything that ever happened with one customer, newest first, across every channel."""
    case = await db.pool().fetchrow(
        "SELECT * FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
        user["tenant_id"], case_key,
    )
    if not case:
        raise HTTPException(404, "Contact not found")
    events = await casetimeline.timeline(user["tenant_id"], case_key, limit=limit)
    leads = await db.pool().fetch(
        "SELECT id, status, channel, message, created_at FROM leads "
        "WHERE tenant_id=$1 AND case_id=$2 ORDER BY created_at DESC LIMIT 50",
        user["tenant_id"], case["id"],
    )
    lead_ids = [row["id"] for row in leads]
    appointments = await db.pool().fetch(
        "SELECT starts_at, status, name FROM appointments "
        "WHERE tenant_id=$1 AND lead_id = ANY($2::uuid[]) ORDER BY starts_at DESC LIMIT 50",
        user["tenant_id"], lead_ids,
    ) if lead_ids else []
    summary = casetimeline.summarise(events)
    return {
        "case_key": case_key,
        "label": casetimeline.contact_label(dict(case)),
        "phone": case["primary_phone"],
        "email": case["primary_email"],
        "automation_paused": bool(case["automation_paused"]),
        "takeover_at": case["takeover_at"].isoformat() if case["takeover_at"] else None,
        **summary,
        "events": [
            {
                "channel": e["channel"],
                "channel_label": casetimeline.CHANNEL_LABELS.get(e["channel"], e["channel"].title()),
                "direction": e["direction"],
                "body": e["body"],
                "occurred_at": e["occurred_at"].isoformat() if e["occurred_at"] else None,
                "answered_at": e["answered_at"].isoformat() if e["answered_at"] else None,
            }
            for e in events
        ],
        "enquiries": [
            {"id": str(row["id"]), "status": row["status"], "channel": row["channel"],
             "message": row["message"],
             "created_at": row["created_at"].isoformat() if row["created_at"] else None}
            for row in leads
        ],
        "appointments": [
            {"starts_at": row["starts_at"].isoformat() if row["starts_at"] else None,
             "status": row["status"], "name": row["name"]}
            for row in appointments
        ],
    }


@app.put("/owner/contacts/{case_key}/takeover")
async def owner_contact_takeover(
    case_key: str, body: ContactTakeover, user: dict = Depends(owner_auth.current_user)
):
    """Pause or resume the assistant for one customer, from the unified timeline.

    Same store as the enquiry-level takeover, so the two screens can never disagree about who is
    handling the customer.
    """
    if body.paused and not body.reason.strip():
        raise HTTPException(422, "Say why you are taking over; it is recorded for the customer's history")
    changed = await casetimeline.set_takeover(
        user["tenant_id"], case_key=case_key, paused=body.paused,
        by=f"{user.get('email') or user.get('role') or 'owner'}: {body.reason}".strip(": "),
    )
    if not changed:
        raise HTTPException(404, "Contact not found")
    return {"paused": body.paused, "case_key": case_key}


@app.post("/owner/crm/leads/{lead_id}/takeover")
async def owner_lead_takeover(
    lead_id: str, body: CaseTakeoverRequest, user: dict = Depends(owner_auth.current_user)
):
    """Take over, or hand back, one customer.

    Pausing stops the assistant replying to that person on every channel, which is what an owner
    needs the moment they start answering themselves. It is deliberately available to any signed-in
    member of the business: the person handling the customer is exactly who needs to press it.
    """
    lead = await db.pool().fetchrow(
        "SELECT case_id FROM leads WHERE tenant_id=$1 AND id=$2::uuid", user["tenant_id"], lead_id)
    if not lead:
        raise HTTPException(404, "Enquiry not found")
    if not lead["case_id"]:
        raise HTTPException(409, "This enquiry has no conversation history to take over yet")

    case = await db.pool().fetchrow(
        "SELECT case_key FROM customer_cases WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], lead["case_id"])
    if not case:
        raise HTTPException(404, "Customer case not found")

    changed = await casetimeline.set_takeover(
        user["tenant_id"], case_key=case["case_key"], paused=body.paused,
        by=str(user.get("email") or user.get("id") or "owner"),
    )
    return {"lead_id": lead_id, "automation_paused": bool(body.paused), "updated": changed}


@app.get("/owner/provider-readiness")
async def owner_provider_readiness(user: dict = Depends(owner_auth.current_user)):
    """What is blocking each provider, and which steps need a person rather than a deployment.

    Reads configuration only and changes nothing. A step marked ready means the software side is
    satisfied; it is NOT a claim that the provider has accepted anything, which only the provider
    can confirm.
    """
    owner_auth.require_role(user, "owner")
    return provider_readiness.report()


@app.post("/owner/auth/logout")
async def owner_logout(request: Request, user: dict = Depends(owner_auth.current_user)):
    await owner_auth.logout(request.headers["authorization"].partition(" ")[2])
    return {"ok": True}


@app.get("/owner/onboarding")
async def owner_onboarding_overview(user: dict = Depends(owner_auth.current_user)):
    try:
        return await owner_onboarding.overview(user["tenant_id"])
    except ValueError:
        raise HTTPException(404, "Business not found") from None


@app.patch("/owner/onboarding/profile")
async def owner_onboarding_update(
    body: owner_onboarding.OwnerBusinessProfile,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    try:
        return await owner_onboarding.update_profile(user["slug"], body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/owner/onboarding/authorizations")
async def owner_channel_authorizations(user: dict = Depends(owner_auth.current_user)):
    return await channel_authorization.authorizations(user["tenant_id"])


@app.post("/owner/knowledge/import-website")
async def owner_import_website(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user['tenant_id'])
    try:
        async with asyncio.timeout(55):
            result = await ingest.ingest_site(tenant, max_pages=15)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        raise HTTPException(503, "Website import could not finish. Existing knowledge is retained; retry or upload business information.") from None
    if not result['chunks']:
        raise HTTPException(422, "No readable pages were imported. Check robots.txt or upload business information.")
    return result


@app.get("/owner/knowledge")
async def owner_knowledge_list(user: dict = Depends(owner_auth.current_user)):
    return await owner_knowledge.documents(user["tenant_id"])


@app.post("/owner/knowledge", status_code=201)
async def owner_knowledge_save(body: owner_knowledge.BusinessDocument,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        return await owner_knowledge.save(user["tenant_id"], body)
    except ValueError:
        raise HTTPException(400, "Business document could not be saved") from None
    except Exception:
        # Do not disclose document text, model/network diagnostics or DB errors.
        raise HTTPException(503, "Document processing is unavailable; your saved information is unchanged") from None


@app.delete("/owner/knowledge/{document_id}")
async def owner_knowledge_delete(document_id: str,
                                 user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await owner_knowledge.remove(user["tenant_id"], document_id):
        raise HTTPException(404, "Business document not found")
    return {"ok": True}


@app.get("/owner/onboarding/brand-suggestion")
async def owner_brand_suggestion(website: str = "",
                                 user: dict = Depends(owner_auth.current_user)):
    """Read the business's own public website and propose its brand.

    The review screen shows this proposal so the owner confirms rather than types.
    Nothing is written: no tenant field, no brand row, no consent. Every uncertain
    answer comes back as a note instead of a guess.
    """
    owner_auth.require_role(user, "owner")
    if not website.strip():
        tenant = await tenants.get_by_id(user["tenant_id"])
        website = (tenant or {}).get("site_url") or ""
    try:
        async with asyncio.timeout(40):
            return await brand_from_site.suggest(website)
    except TimeoutError:
        raise HTTPException(504, "That website took too long to answer. Try again, or enter your details yourself.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        log.exception("brand suggestion failed")
        raise HTTPException(503, "We could not read that website just now. Enter your details yourself; nothing was saved.") from None


@app.get("/owner/onboarding/install-check")
async def owner_install_check(website: str = "",
                              user: dict = Depends(owner_auth.current_user)):
    """Is the chat widget actually on the customer's live page? Read-only."""
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user["tenant_id"]) or {}
    site = website.strip() or (tenant.get("site_url") or "")
    try:
        async with asyncio.timeout(30):
            return await brand_from_site.check_install(site, tenant.get("public_key") or "")
    except TimeoutError:
        raise HTTPException(504, "Your website took too long to answer. Try again in a moment.") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception:
        log.exception("install check failed")
        raise HTTPException(503, "We could not read your website just now. Try again in a moment.") from None


@app.get("/owner/onboarding/inbound-readiness")
async def owner_inbound_readiness(user: dict = Depends(owner_auth.current_user)):
    """Whole-chain check for this tenant's inbound email. Onboarding must not claim
    email is ready unless every link is green: a missing consent row drops real mail."""
    return await inbound_readiness.check(user["tenant_id"])


@app.get("/admin/inbound-readiness", dependencies=admin)
async def admin_inbound_readiness():
    """Operator view across every tenant; used by scripts/vps/check-inbound-chain.sh."""
    return await inbound_readiness.check_all()


@app.get("/owner/inbound-audit")
async def owner_inbound_audit(limit: int = 50, user: dict = Depends(owner_auth.current_user)):
    """Refused and blocked inbound mail for this tenant: who, what and why.

    A count alone told the owner that mail was lost but never which customer sent it.
    """
    _email_feature_gate()
    return await inbound_policy.recent(user["tenant_id"], max(1, min(limit, 200)))


@app.get("/admin/tenants/{slug}/inbound-audit", dependencies=admin)
async def admin_inbound_audit(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    return await inbound_policy.recent(tenant["id"], max(1, min(limit, 200)))


@app.get("/owner/onboarding/authorization-audit")
async def owner_authorization_audit(
    limit: int = 50, user: dict = Depends(owner_auth.current_user),
):
    """Who granted or revoked each channel, and how. The database writes these rows, so a
    direct-SQL change is recorded too (actor_kind='direct') instead of vanishing."""
    return await channel_authorization.audit_log(user["tenant_id"], max(1, min(limit, 200)))


class OperatorAuthorization(channel_authorization.ChannelAuthorization):
    reason: str = Field(min_length=3, max_length=500)


@app.post("/admin/tenants/{slug}/channel-authorizations", dependencies=admin)
async def admin_channel_authorization(
    slug: str, body: OperatorAuthorization, request: Request,
):
    """Record a consent decision on the customer's behalf, attributed to the operator.

    Before this existed consent could only be granted by logging in as the tenant's
    owner, so the audit trail claimed the customer had clicked it. A real owner
    clicking their own consent remains the preferred path; this one at least names
    the person who acted.
    """
    tenant = await _require_tenant(slug)
    operator = (request.headers.get("x-operator") or "").strip()[:200] or "operator-token"
    owner = await channel_authorization.ownership(tenant["id"])
    try:
        result = await channel_authorization.record_authorization(
            tenant["id"], owner["id"] if owner else None, body,
            actor_kind="operator", actor_label=f"{operator}: {body.reason}",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {**result, "operator": operator, "owner_principal": bool(owner)}


@app.get("/admin/tenants/{slug}/authorization-audit", dependencies=admin)
async def admin_authorization_audit(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    return await channel_authorization.audit_log(tenant["id"], max(1, min(limit, 500)))


class PauseRequest(BaseModel):
    paused: bool


@app.get("/owner/pause")
async def owner_pause_state(user: dict = Depends(owner_auth.current_user)):
    """Always readable, so the Studio can show the switch without hunting for a permission."""
    return await tenant_pause.state(user["tenant_id"])


@app.post("/owner/pause")
async def owner_set_pause(body: PauseRequest, user: dict = Depends(owner_auth.current_user)):
    """Stop or resume Concierge for this business only.

    Never the operator's deployment-wide kill switch (flood_guard): one customer must not be able
    to silence another.
    """
    owner_auth.require_role(user, "owner")
    return await tenant_pause.set_paused(
        user["tenant_id"], body.paused, user.get("email") or "owner")


@app.post("/owner/onboarding/authorizations")
async def owner_channel_authorization_update(
    body: channel_authorization.ChannelAuthorization,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    try:
        result = await channel_authorization.record_authorization(
            user["tenant_id"], user["id"], body,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    # Consenting to read email is useless if the inbox is still switched off. A mailbox that was
    # registered before consent existed stays disabled until something re-enables it, which used to
    # mean the operator running SQL by hand while the customer saw "email is not ready".
    if body.authorized and body.channel == "email_read":
        tenant = await tenants.get_by_id(user["tenant_id"])
        if tenant and (tenant.get("reply_address") or "").strip():
            try:
                await reply_address.ensure(tenant)
                result["mailbox"] = "enabled"
            except Exception:  # noqa: BLE001 - the consent must not fail on a routing problem
                log.exception("reply mailbox could not be re-enabled for %s", user.get("slug"))
                result["mailbox"] = "could not be re-enabled automatically"
    return result


class EmailAutoReplyRequest(BaseModel):
    enabled: bool
    acknowledgement: bool = False


@app.post("/owner/onboarding/email-auto-reply")
async def owner_set_email_auto_reply(
    body: EmailAutoReplyRequest,
    user: dict = Depends(owner_auth.current_user),
):
    """Turn automatic email replies on or off for this business, as one auditable action.

    Enabling requires acknowledgement and sets the flag plus BOTH channel authorizations, because a
    reply is only delivered when all three agree. The response reports whether the channel is
    actually ready rather than implying success from the flag alone.
    """
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user["tenant_id"])
    if tenant is None:
        raise HTTPException(404, "Business not found")
    try:
        return await owner_onboarding.set_email_auto_reply(
            tenant, enabled=body.enabled, actor_id=user["id"], acknowledgement=body.acknowledgement,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class NativeBookingRequest(BaseModel):
    enabled: bool
    acknowledgement: bool = False


@app.post("/owner/onboarding/native-booking")
async def owner_set_native_booking(
    body: NativeBookingRequest,
    user: dict = Depends(owner_auth.current_user),
):
    """Turn customer booking on or off, refusing an enable that could never book anything.

    Enabling requires acknowledgement and usable opening hours. Without that check an owner could
    switch booking on with every day closed, and the assistant would answer "no free times" for
    every date the customer asked about -- silent breakage, because nothing raises.
    """
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user["tenant_id"])
    if tenant is None:
        raise HTTPException(404, "Business not found")
    try:
        return await owner_onboarding.set_native_booking(
            tenant, enabled=body.enabled, acknowledgement=body.acknowledgement,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/owner/onboarding/readiness")
async def owner_channel_readiness(user: dict = Depends(owner_auth.current_user)):
    status = await owner_onboarding.overview(user["tenant_id"])
    declarations = await channel_authorization.authorizations(user["tenant_id"])
    settings = get_settings()
    checks = {
        "telephone": status["channels"]["telephone"]["configured"],
        "call_recording": bool(
            (settings.voice_recording_enabled and status["channels"].get("website_voice", {}).get("configured"))
            or (settings.phone_recording_enabled and settings.twilio_account_sid and settings.twilio_auth_token)
        ),
        "email_read": bool(settings.inbound_cloudflare_enabled),
        "email_send": status["channels"]["email"]["configured"],
        "sms_read": status["channels"]["sms"]["configured"],
        "sms_send": status["channels"]["sms"]["configured"],
        "social": status["channels"]["social"]["configured"],
    }
    return {
        "business": status["business"]["name"],
        "channels": channel_authorization.readiness(declarations, checks),
        "customer_activation_enabled": False,
    }


@app.post("/owner/invitations", status_code=201)
async def owner_invite(body: OwnerInvite, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    try:
        token = await owner_auth.make_invite(user["tenant_id"], body.email, body.role)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"invitation_token": token, "invitation_url": owner_auth.invitation_link(token),
            "expires_in_hours": 24}


class TeamRoleIn(BaseModel):
    role: Literal["viewer", "editor", "owner"]


async def _team_member(tenant_id, user_id):
    row = await db.pool().fetchrow(
        "SELECT id, email, role, active FROM tenant_users WHERE tenant_id=$1 AND id=$2",
        tenant_id, user_id)
    if not row:
        raise HTTPException(404, "That person is not on this account")
    return dict(row)


async def _other_active_owner_exists(tenant_id, user_id) -> bool:
    return bool(await db.pool().fetchval(
        "SELECT 1 FROM tenant_users WHERE tenant_id=$1 AND role='owner' AND active AND id<>$2",
        tenant_id, user_id))


@app.get("/owner/team")
async def owner_team(user: dict = Depends(owner_auth.current_user)):
    """Who can get into this workspace, and who has been invited but not arrived yet.

    The list is deliberately plain: email, role, state. A business that shares access needs to see
    it and take it away again -- without this, a departed staff member kept their login forever.
    """
    members = await db.pool().fetch(
        "SELECT id, email, role, active, created_at FROM tenant_users "
        "WHERE tenant_id=$1 ORDER BY active DESC, email", user["tenant_id"])
    invites = await db.pool().fetch(
        "SELECT email, role, expires_at FROM tenant_invites "
        "WHERE tenant_id=$1 AND used_at IS NULL AND expires_at > now() ORDER BY created_at DESC",
        user["tenant_id"])
    return {
        "members": [{"id": str(m["id"]), "email": m["email"], "role": m["role"],
                     "active": m["active"], "created_at": m["created_at"].isoformat()}
                    for m in members],
        "invitations": [{"email": i["email"], "role": i["role"],
                         "expires_at": i["expires_at"].isoformat()} for i in invites],
        "you": str(user["id"]),
    }


@app.patch("/owner/team/{user_id}")
async def owner_team_role(user_id: uuid.UUID, body: TeamRoleIn,
                          user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    target = await _team_member(user["tenant_id"], user_id)
    if target["role"] == "owner" and body.role != "owner":
        if not await _other_active_owner_exists(user["tenant_id"], user_id):
            raise HTTPException(400, "A business needs at least one owner")
    await db.pool().execute(
        "UPDATE tenant_users SET role=$3 WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], user_id, body.role)
    return {"id": str(user_id), "role": body.role}


@app.post("/owner/team/{user_id}/deactivate")
async def owner_team_deactivate(user_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    """Take a person's access away. Their history stays; their login stops working immediately."""
    owner_auth.require_role(user, "owner")
    if str(user_id) == str(user["id"]):
        raise HTTPException(400, "You cannot remove your own access")
    target = await _team_member(user["tenant_id"], user_id)
    if target["role"] == "owner" and not await _other_active_owner_exists(user["tenant_id"], user_id):
        raise HTTPException(400, "A business needs at least one owner")
    await db.pool().execute(
        "UPDATE tenant_users SET active=false WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], user_id)
    # Sessions check `active`, but kill them outright so nothing in flight survives the decision.
    await db.pool().execute("DELETE FROM tenant_sessions WHERE user_id=$1", user_id)
    return {"id": str(user_id), "active": False}


@app.post("/owner/team/{user_id}/reactivate")
async def owner_team_reactivate(user_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    target = await _team_member(user["tenant_id"], user_id)
    await db.pool().execute(
        "UPDATE tenant_users SET active=true WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], user_id)
    return {"id": str(user_id), "active": True, "email": target["email"]}


@app.get("/owner/email-drafts")
async def owner_drafts(
    status: Literal["draft", "approved", "discarded", "quarantined", "all"] = "draft",
    user: dict = Depends(owner_auth.current_user),
):
    _email_feature_gate()
    return await email_drafts.list_drafts(user["tenant_id"], status)


@app.patch("/owner/email-drafts/{draft_id}")
async def owner_edit_draft(
    draft_id: int, body: EmailDraftRevision,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    try:
        row = await email_drafts.revise(user["tenant_id"], draft_id, body.reply_body)
    except email_drafts.DraftError as exc:
        raise HTTPException(400, str(exc))
    if not row:
        raise HTTPException(404, "Draft not found")
    return row


@app.post("/owner/email-drafts/{draft_id}/discard")
async def owner_discard_draft(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    row = await email_drafts.discard(user["tenant_id"], draft_id)
    if not row:
        raise HTTPException(404, "Draft not found")
    await inbound_policy.audit(user["tenant_id"], draft_id, "discarded", user.get("email", ""))
    return row


@app.post("/owner/email-drafts/{draft_id}/approve")
async def owner_approve_draft(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    _email_feature_gate()
    try:
        row = await email_drafts.approve(user["tenant_id"], draft_id)
    except email_drafts.DraftError as exc:
        raise HTTPException(503, str(exc))
    if not row:
        raise HTTPException(409, "Draft unavailable")
    await inbound_policy.audit(user["tenant_id"], draft_id, "approved", user.get("email", ""))
    return row


@app.post("/owner/email-drafts/{draft_id}/release")
async def owner_release_draft(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    """Release a quarantined draft. Owner only: a second pair of eyes on high risk."""
    owner_auth.require_role(user, "owner")
    _email_feature_gate()
    row = await email_drafts.release(user["tenant_id"], draft_id)
    if not row:
        raise HTTPException(404, "No quarantined draft")
    await inbound_policy.audit(user["tenant_id"], draft_id, "released", user.get("email", ""))
    return row


@app.get("/owner/email-sender-rules")
async def owner_sender_rules(user: dict = Depends(owner_auth.current_user)):
    _email_feature_gate()
    return await inbound_policy.list_rules(user["tenant_id"])


@app.post("/owner/email-sender-rules", status_code=201)
async def owner_add_sender_rule(body: SenderRule, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    try:
        row = await inbound_policy.add_rule(
            user["tenant_id"], body.pattern, body.action, user.get("email", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await inbound_policy.audit(user["tenant_id"], None, "rule_added", user.get("email", ""),
                               {"pattern": body.pattern, "action": body.action})
    return row


@app.delete("/owner/email-sender-rules/{rule_id}")
async def owner_remove_sender_rule(rule_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    if not await inbound_policy.remove_rule(user["tenant_id"], rule_id):
        raise HTTPException(404, "Rule not found")
    await inbound_policy.audit(user["tenant_id"], None, "rule_removed", user.get("email", ""),
                               {"rule_id": rule_id})
    return {"removed": True}


@app.get("/owner/phone-setup")
async def owner_phone_setup(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT designated_number,connection,answer_mode,owner_number,status FROM managed_phone_setups WHERE tenant_id=$1",
        user["tenant_id"])
    return dict(row) if row else {"status": "not_requested"}


@app.put("/owner/phone-setup")
async def owner_save_phone_setup(body: managed_phone.PhoneSetup, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await managed_phone.save_setup(user["tenant_id"], body)


@app.get("/owner/phone-numbers")
async def owner_phone_numbers(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT e164,enabled,created_at FROM phone_numbers WHERE tenant_id=$1",
        user["tenant_id"],
    )
    return [dict(row) for row in rows]


@app.get("/owner/sms-phone")
async def owner_sms_phone(user: dict = Depends(owner_auth.current_user)):
    device=await db.pool().fetchrow(
        "SELECT from_number,last_seen,verified_at,inbound_verified_at FROM sms_devices "
        "WHERE tenant_id=$1 AND enabled",user["tenant_id"])
    jobs=await db.pool().fetch(
        "SELECT recipient,body,status,created_at FROM device_sms_jobs "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 20",user["tenant_id"])
    online=bool(device and device["last_seen"] and
                (datetime.now(timezone.utc)-device["last_seen"]).total_seconds()<300)
    return {"paired":bool(device),"online":online,
            "number":device["from_number"] if device else "",
            "send_verified":bool(device and device["verified_at"]),
            "receive_verified":bool(device and device["inbound_verified_at"]),
            "messages":[dict(row) for row in jobs]}


class PhoneSmsTest(BaseModel):
    model_config = {"extra":"forbid"}
    acknowledgement: Literal[True]
    request_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


class MissedCallTextback(BaseModel):
    enabled: bool


@app.get("/owner/missed-calls")
async def owner_missed_calls(limit: int = 20, user: dict = Depends(owner_auth.current_user)):
    """What we did about calls nobody answered, so the owner is never guessing."""
    tenant = await _require_tenant(user["slug"])
    rows = await missed_calls.recent(user["tenant_id"], max(1, min(limit, 100)))
    return {
        "enabled": bool(tenant.get("missed_call_textback")),
        "template": tenant.get("missed_call_template") or "",
        "count_30d": await db.pool().fetchval(
            "SELECT count(*) FROM missed_call_recoveries WHERE tenant_id=$1 AND status='queued' "
            "AND created_at>now()-interval '30 days'", user["tenant_id"]),
        "recoveries": rows,
    }


@app.put("/owner/missed-calls/textback")
async def owner_set_missed_textback(
    body: MissedCallTextback, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    await db.pool().execute(
        "UPDATE tenants SET missed_call_textback=$2 WHERE id=$1", user["tenant_id"], body.enabled)
    return {"enabled": body.enabled}


@app.post("/owner/sms-phone/test",status_code=202)
async def owner_sms_phone_test(body: PhoneSmsTest,user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user,"owner")
    tenant=await _require_tenant(user["slug"])
    previous=await db.pool().fetchval(
        "SELECT id FROM device_sms_jobs WHERE tenant_id=$1 AND request_key LIKE 'phone-test:%' "
        "AND created_at>now()-interval '1 minute' LIMIT 1",user["tenant_id"])
    if previous:
        return {"status":"awaiting_phone_result"}
    try:
        await device_sms.enqueue(tenant,tenant.get("sms_from") or "",
            "Trendi Concierge SMS connection test. No reply needed.","phone-test:"+body.request_id)
    except device_sms.AwaitingReceipt:
        return {"status":"awaiting_phone_result"}
    except ValueError as error:
        raise HTTPException(409,str(error)) from None
    except device_sms.ReconciliationRequired:
        raise HTTPException(409,"Previous phone result needs review before another test") from None
    return {"status":"sent"}


@app.get("/owner/phone-calls")
async def owner_phone_calls(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT call_sid,from_number,to_number,status,started_at,ended_at, "
        "recording_consent,recording_status "
        "FROM phone_calls WHERE tenant_id=$1 ORDER BY started_at DESC LIMIT 100",
        user["tenant_id"],
    )
    return [dict(row) for row in rows]


@app.get("/owner/phone-calls/{call_id}/transcript")
async def owner_phone_transcript(call_id: str,user: dict = Depends(owner_auth.current_user)):
    found=await db.pool().fetchval('SELECT 1 FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2',user['tenant_id'],call_id)
    if not found:
        raise HTTPException(404,'Call not found')
    rows=await db.pool().fetch(
        "SELECT m.role,m.content,m.created_at FROM phone_calls p "
        "JOIN conversations c ON c.tenant_id=p.tenant_id AND c.session_id=p.call_sid AND c.channel='phone' "
        "JOIN messages m ON m.conversation_id=c.id WHERE p.tenant_id=$1 AND p.call_sid=$2 "
        "AND m.role IN ('user','assistant') ORDER BY m.id LIMIT 200",user['tenant_id'],call_id)
    return [dict(row) for row in rows]

# ------------------------------------------------------------------ owner social
# The portal is the identity and approval interface; the Rust service never
# receives a customer browser's auth token, and no social secrets reach the UI.

class OwnerSocialDraft(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    account_ids: list[str] = Field(min_length=1, max_length=10)
    link: str = Field(default="", max_length=2000)
    hashtags: str = Field(default="", max_length=2000)
    media: list[str] = Field(default_factory=list, max_length=10)
    options: dict = Field(default_factory=dict)


class OwnerSocialCompose(OwnerSocialDraft):
    video: str | None = Field(default=None, max_length=2048)


@app.post("/owner/social/media")
async def owner_social_media_upload(request: Request, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    base, key = social_bridge._configuration()
    slug = await social_bridge.ensure_tenant(user)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 64 * 1024 * 1024:
            raise HTTPException(413, "Upload a file smaller than 64 MB")
    import httpx
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        result = await client.post(base+f"/v1/customers/{slug}/media", headers={"Authorization":"Bearer "+key,"Content-Type":"application/octet-stream"},content=bytes(content))
    if result.status_code != 200:
        raise HTTPException(400, "Media could not be processed; use a JPG/PNG image or MP4/MOV video under 64 MB")
    return result.json()


@app.get("/api/v1/social-media/{token}")
async def social_media_download(token: str):
    if len(token)>2048:
        raise HTTPException(404,"Media unavailable")
    base, _ = social_bridge._configuration()
    import httpx
    async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
        result = await client.get(base+"/public-media/"+token)
    if result.status_code != 200:
        raise HTTPException(404,"Media unavailable")
    return Response(content=result.content,media_type=result.headers.get("content-type","application/octet-stream"),headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","X-Robots-Tag":"noindex, nofollow"})


@app.post("/owner/social/compose")
async def owner_social_compose(body: OwnerSocialCompose,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.compose(user, body.model_dump())


class OwnerSocialSchedule(BaseModel):
    scheduled_at: int = Field(ge=0)


@app.get("/owner/social/status")
async def owner_social_status(user: dict = Depends(owner_auth.current_user)):
    # No credentials, client IDs, access tokens or backend hostname in the response.
    providers = {"linkedin_organization": False, "linkedin": False, "facebook": False, "instagram": False, "google_business": False, "tiktok": False, "x": False}
    if settings.social_service_enabled:
        try:
            status = await social_bridge.provider_status()
            providers = {name: status.get(name) is True for name in providers}
        except HTTPException:
            pass
    return {"enabled": bool(settings.social_service_enabled),
            "customer": user["slug"],
            "providers": providers,
            "callback_path": "/owner/social/oauth/callback",
            "live_publishing": False}


@app.post("/owner/social/oauth/renew/{account_id}")
async def owner_social_oauth_renew(account_id: str,
                                  user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.renew_social_token(user, account_id)


class OwnerOAuthCallback(BaseModel):
    state: str = Field(min_length=32, max_length=256)
    code: str = Field(min_length=1, max_length=2048)


@app.post("/owner/social/oauth/tiktok/start")
async def owner_social_tiktok_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_tiktok_oauth(user)


@app.post("/owner/social/oauth/tiktok/finish")
async def owner_social_tiktok_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_tiktok_oauth(user, body.state, body.code)


@app.delete("/owner/social/oauth/tiktok/accounts/{account_id}")
async def owner_social_tiktok_disconnect(account_id: str,
                                         user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_tiktok(user, account_id)


@app.post("/owner/social/oauth/google/start")
async def owner_social_google_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_google_oauth(user)


@app.post("/owner/social/oauth/google/finish")
async def owner_social_google_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_google_oauth(user, body.state, body.code)


@app.delete("/owner/social/oauth/google/accounts/{account_id}")
async def owner_social_google_disconnect(account_id: str,
                                          user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_google(user, account_id)


@app.post("/owner/social/oauth/x/start")
async def owner_social_x_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_x_oauth(user)


@app.post("/owner/social/oauth/x/finish")
async def owner_social_x_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_x_oauth(user, body.state, body.code)


@app.delete("/owner/social/oauth/x/accounts/{account_id}")
async def owner_social_x_disconnect(account_id: str,
                                          user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_x(user, account_id)


@app.post("/owner/social/oauth/meta/{network}/start")
async def owner_social_meta_start(network: str,
                                  user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    return await social_bridge.start_meta_oauth(user, network)


@app.post("/owner/social/oauth/meta/{network}/finish")
async def owner_social_meta_finish(network: str, body: OwnerOAuthCallback,
                                   user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    return await social_bridge.finish_meta_oauth(user, network, body.state, body.code)


@app.delete("/owner/social/oauth/meta/{network}/accounts/{account_id}")
async def owner_social_meta_disconnect(network: str, account_id: str,
                                       user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    return await social_bridge.unlink_meta(user, network, account_id)


@app.delete("/owner/social/oauth/linkedin/accounts/{account_id}")
async def owner_social_linkedin_unlink(
    account_id: str, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    return await social_bridge.unlink_linkedin(user, account_id)


@app.post("/owner/social/oauth/linkedin_organization/start")
async def owner_social_linkedin_organization_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_linkedin_organization_oauth(user)


@app.post("/owner/social/oauth/linkedin_organization/finish")
async def owner_social_linkedin_organization_finish(body: OwnerOAuthCallback, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_linkedin_organization_oauth(user, body.state, body.code)


@app.post("/owner/social/oauth/linkedin/start")
async def owner_social_linkedin_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_linkedin_oauth(user)


@app.post("/owner/social/oauth/linkedin/finish")
async def owner_social_linkedin_finish(body: OwnerOAuthCallback,
                                       user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_linkedin_oauth(user, body.state, body.code)


@app.get("/owner/social/accounts")
async def owner_social_accounts(user: dict = Depends(owner_auth.current_user)):
    return await social_bridge.accounts(user)


@app.get("/owner/social/posts")
async def owner_social_posts(user: dict = Depends(owner_auth.current_user)):
    return await social_bridge.posts(user)


@app.post("/owner/social/posts")
async def owner_social_create(body: OwnerSocialDraft,
                              user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.create_draft(user, body.content, body.account_ids,
                                            body.link, body.hashtags, body.media, body.options)


@app.post("/owner/social/posts/{post_id}/submit")
async def owner_social_submit(post_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.submit_draft(user, post_id)


@app.post("/owner/social/posts/{post_id}/approval-request")
async def owner_social_request_approval(post_id: str, body: OwnerSocialSchedule,
                                        user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.request_approval(user, post_id, body.scheduled_at)


@app.post("/owner/social/approvals/{token}/approve")
async def owner_social_approve(token: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.decide(user, token, True)


@app.post("/owner/social/approvals/{token}/reject")
async def owner_social_reject(token: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.decide(user, token, False)
