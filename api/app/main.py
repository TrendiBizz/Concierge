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
from starlette.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import (
    automation, campaigns, chat as chat_engine, convo, db, email_drafts, enquiries, events, ical, ingest, llm, outbox, sales, scoring, sla,
    phone_relay, owner_auth, owner_onboarding, owner_knowledge, channel_authorization, social_bridge, sms, tasks, tenants, tenant_pause, unsub, voice, cloudflare_inbound, device_sms, phone_sip, managed_phone, voice_records, inbound_policy, voice_internal, products, reply_address, designs, media_studio,
)
from . import cloudflare_auth, inbound_readiness, mobile_connections, quotations, calendar_connection, email_secretary, hermes_ops, brand_from_site, releases, owner_ask
from . import suppressions
from . import engagement
from . import sms_inbox
from . import owner_invites
from . import install_requests
from . import site_enquiry
from . import privacy
from . import platform_billing
from .routers import crm, email, owner_portal, owner_signin, social, telephony
from .routers.owner_portal import (  # noqa: F401 - re-exported for tests and tooling
    COUNTRY_LOCALE, EmailAutoReplyRequest, InstallRequest, NativeBookingRequest, OwnerInvite,
    PauseRequest, PushEndpoint, PushKeys, PushSubscribe, TeamRoleIn, _other_active_owner_exists,
    _team_member, owner_authorization_audit, owner_brand_suggestion, owner_channel_authorization_update,
    owner_channel_authorizations, owner_channel_health, owner_channel_readiness, owner_import_website,
    owner_inbound_audit, owner_inbound_readiness, owner_install_check, owner_install_request,
    owner_install_requests, owner_invite, owner_knowledge_delete, owner_knowledge_list,
    owner_knowledge_save, owner_locale, owner_logout, owner_me, owner_onboarding_overview,
    owner_onboarding_update, owner_pause_state, owner_provider_readiness, owner_push_key,
    owner_push_subscribe, owner_push_test, owner_push_unsubscribe, owner_release, owner_release_seen,
    owner_service_worker, owner_set_email_auto_reply, owner_set_native_booking, owner_set_pause,
    owner_team, owner_team_deactivate, owner_team_reactivate, owner_team_role, owner_test_alert,
    public_version,
)
from .routers.crm import (  # noqa: F401 - re-exported for tests and tooling
    AddressIn, AppointmentUpdate, AskBody, Assignee, BulkAssign, BusinessDetails,
    CaseTakeoverRequest, CompanyBody, CompanyUpdate, ContactTakeover, ImportIn, LeadUpdate,
    OpportunityCreate, OwnerTaskCreate, PaymentSettings, QuotePaymentAction, TaskCreate,
    TaskUpdate, VoiceCopyRequest, WebhookIn, _aware, _case_id_for, _csv_row, _require_company,
    _require_member, admin_appointments, admin_create_task, admin_delete_task, admin_list_tasks,
    admin_pipeline, admin_rescore, admin_sales_summary, admin_scoring, admin_sla,
    admin_update_appointment, admin_update_lead, admin_update_task, calendar_feed,
    owner_add_address, owner_addresses, owner_ask_route, owner_business, owner_business_update,
    owner_companies, owner_company_create, owner_company_delete, owner_company_update,
    owner_contact_assignee, owner_contact_company, owner_contact_takeover, owner_contact_timeline,
    owner_contacts, owner_contacts_bulk_assign, owner_create_opportunity, owner_crm,
    owner_crm_pipeline, owner_crm_recordings, owner_crm_transcript, owner_crm_update,
    owner_delete_webhook, owner_deliver_voice_copy, owner_deliver_webhook, owner_export_contacts,
    owner_get_webhook, owner_import_contacts, owner_lead_assignee, owner_lead_case,
    owner_lead_takeover, owner_payment_settings, owner_quote_payment, owner_remove_address,
    owner_reports_export, owner_revenue, owner_set_payment_settings, owner_set_webhook,
    owner_share_voice_recording, owner_task_create, owner_task_delete, owner_task_update,
    owner_tasks, owner_voice_recording,
)
from .routers.email import (  # noqa: F401 - re-exported for tests and tooling
    CampaignCreate, CampaignSend, EmailDraftCreate, EmailDraftRevision, InboundMailbox,
    ManualSuppression, MarketingConsent, SenderRule, TemplateBody, _campaign_view,
    _email_feature_gate, _plain_page, _require_campaign, admin_cancel_campaign,
    admin_create_campaign, admin_email_draft_approve, admin_email_draft_create,
    admin_email_draft_discard, admin_email_draft_revise, admin_email_drafts, admin_get_campaign,
    admin_list_campaigns, admin_marketing_consent, admin_preview_campaign, admin_send_campaign,
    admin_suppressions, brevo_email_webhook, brevo_email_webhook_status, cloudflare_email_webhook,
    owner_add_sender_rule, owner_add_suppression, owner_approve_draft, owner_discard_draft,
    owner_drafts, owner_edit_draft, owner_email_engagement, owner_release_draft,
    owner_remove_sender_rule, owner_remove_suppression, owner_sender_rules, owner_suppressions,
    owner_template_create, owner_template_delete, owner_template_update, owner_templates,
    register_inbound_mailbox, tracked_link, unsubscribe_do, unsubscribe_page,
)
from .routers.owner_signin import (  # noqa: F401 - re-exported for tests and tooling
    OwnerCodeRequest, OwnerCodeVerify, OwnerEmailLink, OwnerLinkAccept, OwnerLogin, OwnerRedeem,
    owner_accept_invite, owner_email_code, owner_email_link, owner_install_ticket, owner_login,
    owner_redeem, owner_verify_code,
)
from .routers.social import (  # noqa: F401 - re-exported for tests and tooling
    OwnerOAuthCallback, OwnerSocialCompose, OwnerSocialDraft, OwnerSocialSchedule,
    owner_social_accounts, owner_social_approve, owner_social_compose, owner_social_create,
    owner_social_google_disconnect, owner_social_google_finish, owner_social_google_start,
    owner_social_linkedin_finish, owner_social_linkedin_organization_finish,
    owner_social_linkedin_organization_start, owner_social_linkedin_start,
    owner_social_linkedin_unlink, owner_social_media_upload, owner_social_meta_disconnect,
    owner_social_meta_finish, owner_social_meta_start, owner_social_oauth_callback,
    owner_social_oauth_renew, owner_social_posts, owner_social_reject,
    owner_social_request_approval, owner_social_status, owner_social_submit,
    owner_social_tiktok_disconnect, owner_social_tiktok_finish, owner_social_tiktok_start,
    owner_social_x_disconnect, owner_social_x_finish, owner_social_x_start,
    social_media_download,
)
from .routers.telephony import (  # noqa: F401 - re-exported for tests and tooling
    LiveSupervise, LiveTakeover, MissedCallTextback, PhoneNumberCreate, PhoneNumberEnable,
    PhoneSmsTest, ToolRequest, VoiceLogRequest, VoiceTokenRequest, _phone_webhook_form,
    _send_reply, _sms_reply, _twiml, admin_phone_call_history, admin_phone_number_create,
    admin_phone_number_enable, admin_phone_numbers, admin_phone_setup, owner_call_insights,
    owner_live_call, owner_live_calls, owner_live_supervise, owner_live_supervise_stop,
    owner_live_takeover, owner_missed_calls, owner_phone_calls, owner_phone_numbers,
    owner_phone_setup, owner_phone_transcript, owner_save_phone_setup, owner_set_missed_textback,
    owner_sms_phone, owner_sms_phone_test, owner_supervision, private_audio_response,
    shared_voice_recording, sms_inbound, smsgate_inbound, tool_endpoint, twilio_phone_ended,
    twilio_phone_inbound, twilio_phone_recording_receipt, twilio_phone_relay, voice_log,
    voice_recording_upload, voice_session_finish, voice_token,
)
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
    await db.close()


app = FastAPI(title="Website AI Concierge", lifespan=lifespan)

app.include_router(voice_internal.router)
app.include_router(owner_signin.router)
app.include_router(owner_portal.router)
app.include_router(social.router)
app.include_router(telephony.router)
app.include_router(email.router)
app.include_router(crm.router)
app.include_router(device_sms.router)
app.include_router(sms_inbox.router)
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
    daily_summary: bool | None = None                                  # 7am "what needs you today" email to notify_email
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


# ------------------------------------------------- tenant-owner access (separate from operator)
class OwnerRecovery(BaseModel):
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


@app.get("/", include_in_schema=False)
async def owner_root():
    """Types of the bare host: send people to the Studio, the customer sign-in.

    Before this, https://concierge.trendibizz.com/ answered 404 and a visitor had no way
    forward except guessing the path. Found by the 2026-11-14 site audit.
    """
    return RedirectResponse("/studio/", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
async def owner_favicon():
    """Browsers ask for this on every page; a 404 was the only error in the owner app console."""
    icon = STATIC_DIR / "favicon.svg"
    if not icon.is_file():
        return Response(status_code=204)
    return FileResponse(icon, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/owner-ui")
async def owner_ui():
    return FileResponse(
        STATIC_DIR / "owner.html", media_type="text/html",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"},
    )


@app.get("/owner/qrcode.js", include_in_schema=False)
async def owner_qr_library():
    """The QR encoder the owner page uses to turn an invitation link into a scannable code.

    Served under /owner/ because that is the only prefix the public proxy forwards, and cached
    like a static asset: the file is part of the build, not customer data.
    """
    return FileResponse(STATIC_DIR / "qrcode.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=86400",
                                 "X-Content-Type-Options": "nosniff"})


STUDIO_DIR = Path("/srv/studio")


@app.get("/studio", include_in_schema=False)
@app.get("/studio/", include_in_schema=False)
async def studio_page():
    return _studio_index(STUDIO_DIR.resolve())


@app.get("/studio/assets/{path:path}", include_in_schema=False)
async def studio_asset(path: str):
    target = (STUDIO_DIR / "assets" / path).resolve()
    if not str(target).startswith(str((STUDIO_DIR / "assets").resolve())):
        raise HTTPException(404, "Not found")
    if not _readable(target):
        raise HTTPException(404, "Not found")
    # Vite emits content-addressed filenames, so an asset can be cached forever: a new build
    # produces new names. Without this the browser guessed, and a tab opened before a deploy
    # asked for a chunk the deploy had already removed — the lazy-loaded page then went blank.
    return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})



def _readable(path) -> bool:
    """Can this file actually be opened right now?

    `is_file()` answers "does a regular file exist", which is not the same question. During a
    deploy the file exists but can be unreadable for a second (rsync writes it with the uploading
    user's permissions before the chmod), and the old code raised PermissionError straight out of
    the route: every request got a bare "Internal Server Error" instead of the app. Measured in
    production on 2026-11-14: eight 500s on /studio/index.html during one rsync.
    """
    try:
        if not path.is_file():
            return False
        with open(path, "rb"):
            return True
    except OSError:
        return False


def _studio_index(root):
    """Serve the shell, or say plainly that it is being updated. Never a 500."""
    index = root / "index.html"
    if _readable(index):
        return FileResponse(index, media_type="text/html",
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow, noai, noimageai"})
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>One moment</title>"
        "<body style=\"font:16px system-ui;padding:48px;max-width:38rem;margin:auto\">"
        "<h1>One moment</h1><p>We are updating the app. Refresh this page in a few seconds.</p>",
        status_code=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})


@app.get("/studio/install", include_in_schema=False)
@app.get("/studio/install/", include_in_schema=False)
async def studio_install():
    """The install page, served as its own document.

    It used to be a route inside the SPA, which meant a scan could land on the sign-in screen
    (a stored session, a stale bundle, or simply the auth gate) and ask for an email address —
    reported 2026-11-16 from a phone. This document has no router and no auth: the only thing it
    can be is the install offer.
    """
    target = (STUDIO_DIR / "install.html").resolve()
    if _readable(target):
        return FileResponse(target, media_type="text/html",
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow, noai, noimageai"})
    # A deploy that has not copied install.html yet still serves something sensible.
    return _studio_index(STUDIO_DIR.resolve())


_TICKET = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


@app.get("/studio/manifest.webmanifest", include_in_schema=False)
async def studio_manifest(k: str = ""):
    """The app manifest, with the sign-in ticket carried into the installed app's start URL.

    iPhone gives a home-screen app its own empty storage, and the app launches at `start_url`.
    Putting the install-QR ticket in that URL's fragment lets the first launch sign itself in
    (the SPA already redeems `#invite=`), so there is no sign-in step to paste into. The ticket is
    one hour and the fragment never reaches a server log.
    """
    target = (STUDIO_DIR / "manifest.webmanifest").resolve()
    if not _readable(target):
        raise HTTPException(404, "Not found")
    manifest = json.loads(target.read_text(encoding="utf-8"))
    if _TICKET.fullmatch(k or ""):
        manifest["start_url"] = f"/studio/#invite={k}"
    return Response(json.dumps(manifest), media_type="application/manifest+json",
                    headers={"Cache-Control": "no-store"})


@app.get("/studio/{path:path}", include_in_schema=False)
async def studio_file(path: str):
    root = STUDIO_DIR.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not _readable(target):
        # A browser navigating to an app URL gets the shell; a missing *file* must be an honest
        # 404. Answering every missing path with index.html made /studio/sw.js a 200 text/html
        # document: a browser still holding the old worker fetches it for an update, rejects it on
        # the MIME type, and the stale worker can never be replaced (measured live 2026-11-15,
        # against the previous record's claim that the old worker URL 404'd). The SPA has no
        # client-side routes, so no real page lives at a path with a dot in its last segment.
        name = path.rsplit("/", 1)[-1]
        if "." in name:
            raise HTTPException(404, "Not found")
        return _studio_index(root)
    if path.endswith('sw-v2.js'):
        # The worker script must be revalidated on every visit, or a cached copy keeps a browser on
        # an old build indefinitely (measured: Cloudflare served a HIT with no Cache-Control at all).
        return FileResponse(target, media_type="text/javascript",
                            headers={"Cache-Control": "no-cache",
                                     "Service-Worker-Allowed": "/studio/"})
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


from . import webpush  # noqa: E402, F401 - re-exported for tests and tooling
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


@app.post("/admin/tenants/{slug}/test-alert", dependencies=admin, status_code=202)
async def admin_test_alert(slug: str):
    tenant = await _require_tenant(slug)
    result = await channel_health.send_test_alert(tenant)
    return {**result, "go_live_blockers": await channel_health.go_live_blockers(tenant)}


class SiteEnquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["seo", "concierge"]
    email: str = Field(max_length=320)
    name: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=4000)
    plan: str = Field(default="", max_length=20)
    channels: list[str] = Field(default_factory=list, max_length=12)
    referral: str = Field(default="", max_length=64)
    trap: str = Field(default="", max_length=200)


@app.post("/api/enquiry", include_in_schema=False)
async def website_enquiry(body: SiteEnquiry, request: Request):
    """The public website's enquiry forms. No account; stored first, emailed second."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "")
    try:
        return await site_enquiry.submit(
            **body.model_dump(), ip=ip, user_agent=request.headers.get("user-agent", ""))
    except site_enquiry.Refused as error:
        raise HTTPException(error.status, str(error)) from None


@app.get("/admin/site-enquiries", dependencies=admin)
async def admin_site_enquiries(status: str = ""):
    return await site_enquiry.list_all(status)


# ------------------------------------------- installing the chat on their site


@app.get("/admin/install-requests", dependencies=admin)
async def admin_install_requests(status: str = ""):
    return await install_requests.list_all(status)


@app.post("/admin/install-requests/{request_id}/status", dependencies=admin)
async def admin_install_request_status(request_id: str, status: str = "done"):
    try:
        return await install_requests.set_status(request_id, status)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@app.post("/admin/releases/announce", dependencies=admin)
async def admin_release_announce(version: int = releases.CURRENT_VERSION, send: bool = False):
    """Email each business once about a release. Lists who would get it unless send=true."""
    try:
        return await releases.announce(version, dry_run=not send)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@app.get("/admin/inbound-readiness", dependencies=admin)
async def admin_inbound_readiness():
    """Operator view across every tenant; used by scripts/vps/check-inbound-chain.sh."""
    return await inbound_readiness.check_all()


@app.get("/admin/tenants/{slug}/inbound-audit", dependencies=admin)
async def admin_inbound_audit(slug: str, limit: int = 100):
    tenant = await _require_tenant(slug)
    return await inbound_policy.recent(tenant["id"], max(1, min(limit, 200)))


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


@app.get("/admin/pending-invites")
async def admin_pending_invites():
    """Owners who were invited and have never signed in: the call list, not a report.

    An "opened the email" flag is deliberately absent. The question that matters is whether the
    person signed in, and that is recorded to the second by tenant_invites.used_at.
    """
    rows = await db.pool().fetch(
        """
        SELECT t.slug, t.name, i.email, i.created_at AS invited_at, i.expires_at,
               (SELECT max(o.sent_at) FROM outbox o
                 WHERE o.tenant_id=t.id AND o.kind IN ('owner_alert','owner_invite')
                   AND lower(o.to_addr)=lower(i.email)) AS last_email_sent,
               (SELECT max(e.created_at) FROM email_engagement e
                 WHERE e.tenant_id=t.id AND lower(coalesce(e.to_addr,''))=lower(i.email)) AS last_engaged
          FROM tenants t
          JOIN LATERAL (SELECT * FROM tenant_invites WHERE tenant_id=t.id
                         ORDER BY created_at DESC LIMIT 1) i ON true
         WHERE i.used_at IS NULL
         ORDER BY i.created_at
        """)
    return [dict(r) for r in rows]
