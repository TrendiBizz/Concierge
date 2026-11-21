"""Operator / admin routes: tenant lifecycle, outbound kill switch, crawling/ingest, leads/outbox/
conversations/stats, owner invitations/recovery/pending invites, channel authorizations, inbound
readiness/audit, site enquiries, install requests, releases, and test alerts.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import logging
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import (
    channel_authorization, channel_health, db, flood_guard, inbound_policy,
    inbound_readiness, ingest, install_requests, llm, mailer, owner_auth,
    owner_invites, public_fetch, releases, reply_address, scoring, site_enquiry, tenants,
)
from ..booking import DAYS
from ..security import require_admin
from .owner_portal import OwnerInvite

log = logging.getLogger("concierge")
router = APIRouter()
admin = [Depends(require_admin)]


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


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

    @field_validator("lead_webhook_url")
    @classmethod
    def _lead_webhook(cls, value):
        if value is None or not value.strip():
            return value
        cleaned = value.strip()
        public_fetch.validate_public_https_url(cleaned)
        return cleaned


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
    team_chat_webhook_url: str | None = None                           # Slack / Teams incoming webhook ("" clears)

    @field_validator("team_chat_webhook_url")
    @classmethod
    def _team_chat_webhook(cls, value):
        from .. import team_chat_alerts
        return team_chat_alerts.validate_url(value)

    @field_validator("lead_webhook_url")
    @classmethod
    def _lead_webhook(cls, value):
        if value is None or not value.strip():
            return value
        cleaned = value.strip()
        public_fetch.validate_public_https_url(cleaned)
        return cleaned

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


@router.post("/admin/tenants", dependencies=admin)
async def admin_create_tenant(body: TenantCreate):
    data = body.model_dump()
    tenant = await tenants.create(data.pop("name"), data.pop("site_url"), slug=data.pop("slug"), **data)
    try:
        tenant = await reply_address.ensure(tenant)
    except Exception:  # noqa: BLE001 - tenant exists; the operator can retry routing
        log.exception("reply address setup failed for %s", tenant["slug"])
    return _main()._with_snippet(tenant)


@router.get("/admin/tenants", dependencies=admin)
async def admin_list_tenants():
    m = _main()
    return [m._with_snippet(t) for t in await tenants.list_all()]


@router.get("/admin/status", dependencies=admin)
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


@router.get("/admin/outbound/status", dependencies=admin)
async def admin_outbound_status():
    """Paused or not, volumes against the limits, and what the flood guard blocked."""
    return await flood_guard.status()


@router.post("/admin/outbound/pause", dependencies=admin)
async def admin_outbound_pause():
    """Kill switch: stop ALL email and text sending now. Everything stays queued."""
    await flood_guard.set_paused(True, "admin")
    return {"paused": True}


@router.post("/admin/outbound/resume", dependencies=admin)
async def admin_outbound_resume():
    await flood_guard.set_paused(False, "admin")
    return {"paused": False}


@router.post("/admin/tenants/{slug}/rotate-key", dependencies=admin)
async def admin_rotate_key(slug: str):
    """Retire a business's install key: the old snippet stops working at once.

    The key in the embed snippet had no way to be replaced other than deleting the business, so a
    retired prototype kept answering and kept taking enquiries nobody read.
    """
    tenant = await db.pool().fetchrow("SELECT id FROM tenants WHERE slug=$1", slug)
    if not tenant:
        raise HTTPException(404, "No such business")
    key = await tenants.rotate_key(tenant["id"])
    base = _main().get_settings().public_base_url.rstrip("/")
    return {"slug": slug, "public_key": key,
            "embed_snippet": f'<script src="{base}/widget.js" data-key="{key}" defer></script>'}


@router.get("/admin/tenants/{slug}", dependencies=admin)
async def admin_get_tenant(slug: str):
    m = _main()
    tenant = await tenants.ensure_calendar_token(await m._require_tenant(slug))
    chunks = await db.pool().fetchval("SELECT count(*) FROM chunks WHERE tenant_id = $1", tenant["id"])
    return {**m._with_snippet(tenant), "chunk_count": chunks}


@router.patch("/admin/tenants/{slug}", dependencies=admin)
async def admin_update_tenant(slug: str, body: TenantUpdate, force: bool = False):
    m = _main()
    current = await m._require_tenant(slug)
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
    return m._with_snippet(updated)


@router.delete("/admin/tenants/{slug}", dependencies=admin)
async def admin_delete_tenant(slug: str):
    if not await tenants.delete(slug):
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return {"ok": True}


@router.post("/admin/tenants/{slug}/clone", dependencies=admin)
async def admin_clone_tenant(slug: str, body: CloneRequest):
    """Snapshot: copy settings (persona, hours, SMS template...) to a new client. No knowledge or contacts."""
    m = _main()
    source = await m._require_tenant(slug)
    return m._with_snippet(await tenants.clone(source, body.name, body.site_url, body.slug))


class CrawlRequest(BaseModel):
    max_pages: int = Field(default=40, ge=1, le=300)


async def _crawl_job(tenant: dict, max_pages: int) -> None:
    try:
        await ingest.ingest_site(tenant, max_pages=max_pages)
    except Exception:
        log.exception("crawl failed for %s", tenant["slug"])


@router.post("/admin/tenants/{slug}/crawl", dependencies=admin, status_code=202)
async def admin_crawl(slug: str, body: CrawlRequest, background: BackgroundTasks):
    tenant = await _main()._require_tenant(slug)
    if not tenant.get("site_url"):
        raise HTTPException(status_code=400, detail="Tenant has no site_url")
    background.add_task(_crawl_job, tenant, body.max_pages)
    return {"status": "started", "hint": "Check chunk_count on GET /admin/tenants/{slug}"}


class IngestTextRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80, pattern="^[A-Za-z0-9_.-]+$")
    title: str = ""
    text: str = Field(min_length=1, max_length=200_000)


@router.post("/admin/tenants/{slug}/ingest-text", dependencies=admin)
async def admin_ingest_text(slug: str, body: IngestTextRequest):
    tenant = await _main()._require_tenant(slug)
    return await ingest.ingest_text(tenant, body.label, body.text, body.title)


@router.post("/admin/tenants/{slug}/demo-questions", dependencies=admin)
async def admin_demo_questions(slug: str):
    tenant = await _main()._require_tenant(slug)
    try:
        return {"questions": await ingest.generate_demo_questions(tenant)}
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")


@router.get("/admin/tenants/{slug}/leads", dependencies=admin)
async def admin_leads(slug: str, limit: int = 100, min_score: int = 0):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM leads WHERE tenant_id = $1 AND score >= $3 ORDER BY created_at DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 500), max(min_score, 0),
    )
    return [dict(r) for r in rows]


@router.get("/admin/tenants/{slug}/outbox", dependencies=admin)
async def admin_outbox(slug: str, limit: int = 100):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT id, kind, channel, to_addr, status, attempts, last_error, send_at, sent_at "
        "FROM outbox WHERE tenant_id = $1 ORDER BY id DESC LIMIT $2",
        tenant["id"], min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@router.get("/admin/tenants/{slug}/conversations", dependencies=admin)
async def admin_conversations(slug: str, limit: int = 50):
    """Recent conversations with their transcripts - review these monthly to improve the knowledge base."""
    tenant = await _main()._require_tenant(slug)
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


@router.get("/admin/tenants/{slug}/stats", dependencies=admin)
async def admin_stats(slug: str, days: int = 30):
    m = _main()
    return await m._stats(await m._require_tenant(slug), days)


@router.get("/admin/capabilities", dependencies=admin)
async def admin_capabilities():
    return {"email_drafts": _main().settings.email_drafts_enabled}


# ------------------------------------------------- tenant-owner access (separate from operator)
class OwnerRecovery(BaseModel):
    email: str = Field(max_length=320)


@router.post("/admin/tenants/{slug}/owner-invitations", dependencies=admin, status_code=201)
async def admin_invite_owner(slug: str, body: OwnerInvite):
    tenant = await _main()._require_tenant(slug)
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


@router.post("/admin/tenants/{slug}/owner-recovery", dependencies=admin)
async def admin_owner_recovery(slug: str, body: OwnerRecovery):
    tenant = await _main()._require_tenant(slug)
    try:
        link = await owner_auth.owner_link(tenant["id"], body.email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"recovery_token": link["token"], "invitation_url": owner_auth.invitation_link(link["token"]),
            "purpose": link["purpose"], "role": link["role"], "expires_in_hours": 24}


@router.post("/admin/tenants/{slug}/owner-invite", dependencies=admin)
async def admin_owner_invite(slug: str, body: OwnerRecovery):
    """Send a client owner their sign-in link — queued in the outbox, so it is recorded and retried."""
    if not _main().get_settings().email_configured:
        raise HTTPException(503, "Email is not configured on this deployment")
    try:
        result = await owner_invites.send(slug, body.email)
    except ValueError:
        raise HTTPException(404, "No such business") from None
    if not result["queued"]:
        raise HTTPException(409, "An invitation is already queued for that address")
    return result


@router.post("/admin/tenants/{slug}/test-alert", dependencies=admin, status_code=202)
async def admin_test_alert(slug: str):
    tenant = await _main()._require_tenant(slug)
    result = await channel_health.send_test_alert(tenant)
    return {**result, "go_live_blockers": await channel_health.go_live_blockers(tenant)}


@router.get("/admin/site-enquiries", dependencies=admin)
async def admin_site_enquiries(status: str = ""):
    return await site_enquiry.list_all(status)


@router.get("/admin/install-requests", dependencies=admin)
async def admin_install_requests(status: str = ""):
    return await install_requests.list_all(status)


@router.post("/admin/install-requests/{request_id}/status", dependencies=admin)
async def admin_install_request_status(request_id: str, status: str = "done"):
    try:
        return await install_requests.set_status(request_id, status)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.post("/admin/releases/announce", dependencies=admin)
async def admin_release_announce(version: int = releases.CURRENT_VERSION, send: bool = False):
    """Email each business once about a release. Lists who would get it unless send=true."""
    try:
        return await releases.announce(version, dry_run=not send)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("/admin/inbound-readiness", dependencies=admin)
async def admin_inbound_readiness():
    """Operator view across every tenant; used by scripts/vps/check-inbound-chain.sh."""
    return await inbound_readiness.check_all()


@router.get("/admin/tenants/{slug}/inbound-audit", dependencies=admin)
async def admin_inbound_audit(slug: str, limit: int = 100):
    tenant = await _main()._require_tenant(slug)
    return await inbound_policy.recent(tenant["id"], max(1, min(limit, 200)))


class OperatorAuthorization(channel_authorization.ChannelAuthorization):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/admin/tenants/{slug}/channel-authorizations", dependencies=admin)
async def admin_channel_authorization(
    slug: str, body: OperatorAuthorization, request: Request,
):
    """Record a consent decision on the customer's behalf, attributed to the operator.

    Before this existed consent could only be granted by logging in as the tenant's
    owner, so the audit trail claimed the customer had clicked it. A real owner
    clicking their own consent remains the preferred path; this one at least names
    the person who acted.
    """
    tenant = await _main()._require_tenant(slug)
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


@router.get("/admin/tenants/{slug}/authorization-audit", dependencies=admin)
async def admin_authorization_audit(slug: str, limit: int = 100):
    tenant = await _main()._require_tenant(slug)
    return await channel_authorization.audit_log(tenant["id"], max(1, min(limit, 500)))


@router.get("/admin/pending-invites")
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
