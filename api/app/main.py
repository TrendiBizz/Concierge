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
from . import cloudflare_auth, inbound_readiness, mobile_connections, quotations, calendar_connection, email_secretary, brand_from_site, releases, owner_ask
from . import suppressions
from . import engagement
from . import chat_inbox, sms_inbox
from . import owner_invites
from . import install_requests
from . import site_enquiry
from . import privacy, privacy_retention
from . import platform_billing
from . import subscription
from . import api_keys, integrations, owner_mfa, admin_operators, voice_routing, crawl_scheduler, booking_links, email_domain
from .routers import (
    admin as admin_router, crm, email, owner_portal, owner_signin, public, social, telephony,
)
from .routers.public import (  # noqa: F401 - re-exported for tests and tooling
    ChatRequest, PublicTranslateRequest, SiteEnquiry, _GOOGLE_LOCALE, _TICKET,
    _google_translate, _money, _readable, _studio_index, _translate_hits, admin_ui, chat,
    chat_stream, client_report, demo_page, healthz, onboarding_page, owner_favicon,
    owner_qr_library, owner_root, owner_ui, public_translate, robots_txt, studio_asset,
    studio_file, studio_install, studio_manifest, studio_page, website_enquiry, widget_config,
    widget_js, widget_logo,
)
from .routers.admin import (  # noqa: F401 - re-exported for tests and tooling
    CloneRequest, CrawlRequest, IngestTextRequest, OperatorAuthorization, OwnerRecovery,
    TenantCreate, TenantUpdate, _crawl_job, admin_authorization_audit, admin_capabilities,
    admin_channel_authorization, admin_clone_tenant, admin_conversations, admin_crawl,
    admin_create_tenant, admin_delete_tenant, admin_demo_questions, admin_get_tenant,
    admin_inbound_audit, admin_inbound_readiness, admin_ingest_text, admin_install_request_status,
    admin_install_requests, admin_invite_owner, admin_leads, admin_list_tenants, admin_outbox,
    admin_outbound_pause, admin_outbound_resume, admin_outbound_status, admin_owner_invite,
    admin_owner_recovery, admin_pending_invites, admin_release_announce, admin_rotate_key,
    admin_site_enquiries, admin_stats, admin_status, admin_test_alert, admin_update_tenant,
)
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
    _send_reply, _sms_reply, admin_phone_call_history, admin_phone_number_create,
    admin_phone_number_enable, admin_phone_numbers, admin_phone_setup, owner_call_insights,
    owner_live_call, owner_live_calls, owner_live_supervise, owner_live_supervise_stop,
    owner_live_takeover, owner_missed_calls, owner_phone_calls, owner_phone_numbers,
    owner_phone_setup, owner_phone_transcript, owner_save_phone_setup, owner_set_missed_textback,
    owner_sms_phone, owner_sms_phone_test, owner_supervision, private_audio_response,
    shared_voice_recording, smsgate_inbound, tool_endpoint, twilio_phone_ended,
    twilio_phone_inbound, twilio_phone_recording_receipt, twilio_phone_relay, voice_log,
    voice_recording_upload, voice_session_finish, voice_token,
)
from . import invoices
from . import guides
from . import quote_profiles
from . import portability
from . import channel_health, flood_guard, mailer
from . import asterisk_ami, call_control, call_insights, casetimeline, case_policy, live_calls, missed_calls, provider_readiness, voicemail_fallback, quote_payments, revenue, supervision
from .booking import DAYS
from .config import get_settings
from .contact import normalize_phone
from .security import RateLimiter, apply_security_headers, require_admin
from .tools import run_tool

from .observability import configure, RequestTelemetry

configure()
log = logging.getLogger("concierge")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

settings = get_settings()
ip_limiter = RateLimiter(settings.chat_rate_per_minute_ip, 60)
session_limiter = RateLimiter(settings.chat_rate_per_day_session, 86_400)
poll_ip_limiter = RateLimiter(120, 60)
poll_session_limiter = RateLimiter(30, 60)
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
    workers: list[asyncio.Task] = [
        asyncio.create_task(maintain_voice_records(), name="voice_retention_worker"),
        asyncio.create_task(privacy_retention.run_forever(stop), name="privacy_retention_worker"),
        asyncio.create_task(email_secretary.run_forever(stop), name="email_worker"),
        asyncio.create_task(calendar_connection.run_forever(stop), name="calendar_worker"),
        asyncio.create_task(subscription.run_forever(stop), name="billing_grace_worker"),
        asyncio.create_task(portability.run_forever(stop), name="webhook_retry_worker"),
        asyncio.create_task(crawl_scheduler.run_forever(stop), name="crawl_scheduler_worker"),
    ]
    if settings.outbox_enabled:
        workers.extend([
            asyncio.create_task(outbox.run_forever(stop), name="outbox_worker"),
            asyncio.create_task(sla.run_forever(stop), name="sla_worker"),
            asyncio.create_task(sales.run_forever(stop), name="digest_worker"),
            asyncio.create_task(missed_calls.run_forever(stop), name="missed_worker"),
            asyncio.create_task(voicemail_fallback.run_forever(stop), name="voicemail_worker"),
            asyncio.create_task(call_insights.run_forever(stop), name="insights_worker"),
        ])
    try:
        yield
    finally:
        stop.set()
        try:
            results = await asyncio.wait_for(asyncio.gather(*workers, return_exceptions=True), timeout=15.0)
            for task, result in zip(workers, results):
                if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                    log.warning("Background worker %s exited with error during shutdown: %s", task.get_name(), result)
        except asyncio.TimeoutError:
            log.warning("Timed out waiting for background workers; cancelling remaining tasks")
            for task in workers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        bg = [t for t in list(events._background) if not t.done()]
        if bg:
            try:
                await asyncio.wait_for(asyncio.gather(*bg, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                for t in bg:
                    t.cancel()
                await asyncio.gather(*bg, return_exceptions=True)
        await db.close()


app = FastAPI(title="Website AI Concierge", lifespan=lifespan)
app.add_middleware(RequestTelemetry)

app.include_router(voice_internal.router)
app.include_router(owner_signin.router)
app.include_router(owner_mfa.router)
app.include_router(owner_portal.router)
app.include_router(crawl_scheduler.router)
app.include_router(admin_operators.router)
app.include_router(social.router)
app.include_router(telephony.router)
app.include_router(email.router)
app.include_router(crm.router)
app.include_router(admin_router.router)
app.include_router(public.router)
app.include_router(device_sms.router)
app.include_router(sms_inbox.router)
app.include_router(chat_inbox.router)
app.include_router(phone_sip.router)
app.include_router(voice_routing.router)
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
app.include_router(subscription.router)
app.include_router(api_keys.owner_router)
app.include_router(api_keys.api_router)
app.include_router(integrations.owner_router)
app.include_router(integrations.callback_router)
app.include_router(booking_links.owner_router)
app.include_router(booking_links.public_router)
app.include_router(designs.router)
app.include_router(designs.public_router)
app.include_router(designs.page_router)
app.include_router(media_studio.router)
app.include_router(calendar_connection.router)
app.include_router(email_secretary.router)
app.include_router(email_domain.router)

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
    """Same-origin owner portal; no third-party browser access to owner APIs; baseline security headers."""
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
        apply_security_headers(path, response)
        return response
    response = await call_next(request)
    apply_security_headers(path, response)
    return response


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


def _poll_rate_limit(request: Request, session_id: str | None = None) -> None:
    ip = request.client.host if request.client else "unknown"
    if not poll_ip_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Too many poll requests, please slow down")
    if session_id and not poll_session_limiter.check(session_id):
        raise HTTPException(status_code=429, detail="Poll rate limit reached")


# ------------------------------------------------------------ shared stats & tenant helpers
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


admin = [Depends(require_admin)]
STUDIO_DIR = Path("/srv/studio")


def _with_snippet(tenant: dict) -> dict:
    base = settings.public_base_url
    return {
        **tenant,
        "embed_snippet": f'<script src="{base}/widget.js" data-key="{tenant["public_key"]}" defer></script>',
        "demo_url": f"{base}/demo/{tenant['slug']}?presenter=1",
        "report_url": f"{base}/report/{tenant['report_token']}",
        "sms_webhook_url": f"{base}/api/v1/smsgate/{tenant['public_key']}",
        "calendar_url": f"{base}/api/v1/calendar/{tenant['calendar_token']}.ics" if tenant.get("calendar_token") else None,
    }


async def _require_tenant(slug: str) -> dict:
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant


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
