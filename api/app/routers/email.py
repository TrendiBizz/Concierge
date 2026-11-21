"""Email routes: campaigns, unsubscribe, email drafts (admin + owner), inbound mailboxes,
Cloudflare inbound webhook, tracked links, Brevo delivery webhook, suppressions, saved reply
templates, sender rules, and email engagement.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import hmac
import html
import json
import logging
import sys
from typing import Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from .. import (
    campaigns, cloudflare_inbound, db, email_drafts, engagement, flood_guard,
    inbound_policy, llm, owner_auth, suppressions, tenants, unsub,
)
from ..security import require_admin

log = logging.getLogger("concierge")
router = APIRouter()
admin = [Depends(require_admin)]


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


# ------------------------------------------------------------------ campaigns
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


@router.post("/admin/tenants/{slug}/campaigns", dependencies=admin, status_code=201)
async def admin_create_campaign(slug: str, body: CampaignCreate):
    """Create a DRAFT campaign and return who it would reach. Nothing is sent."""
    tenant = await _main()._require_tenant(slug)
    try:
        campaign = await campaigns.create(
            tenant, body.name, body.channel, body.subject, body.body,
            body.model_dump(include={"older_than_days", "statuses", "min_score", "max_recipients"}),
        )
    except campaigns.CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"campaign": _campaign_view(campaign), "preview": await campaigns.preview(tenant, campaign)}


@router.get("/admin/tenants/{slug}/campaigns", dependencies=admin)
async def admin_list_campaigns(slug: str):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM campaigns WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 100", tenant["id"])
    return [{**_campaign_view(dict(r)), "delivery": await campaigns.stats(r["id"])} for r in rows]


@router.get("/admin/campaigns/{campaign_id}/preview", dependencies=admin)
async def admin_preview_campaign(campaign_id: int):
    campaign, tenant = await _require_campaign(campaign_id)
    return await campaigns.preview(tenant, campaign)


@router.post("/admin/campaigns/{campaign_id}/send", dependencies=admin)
async def admin_send_campaign(campaign_id: int, body: CampaignSend):
    """Queue the campaign. `expected_recipients` must match the preview's recipient count."""
    campaign, tenant = await _require_campaign(campaign_id)
    try:
        return await campaigns.send(tenant, campaign, body.expected_recipients)
    except campaigns.CampaignError as exc:
        raise HTTPException(status_code=409 if str(exc).startswith("Audience changed") else 400, detail=str(exc))


@router.post("/admin/campaigns/{campaign_id}/cancel", dependencies=admin)
async def admin_cancel_campaign(campaign_id: int):
    campaign, _ = await _require_campaign(campaign_id)
    return {"cancelled_pending": await campaigns.cancel(campaign)}


@router.get("/admin/campaigns/{campaign_id}", dependencies=admin)
async def admin_get_campaign(campaign_id: int):
    campaign, _ = await _require_campaign(campaign_id)
    return {**_campaign_view(campaign), "delivery": await campaigns.stats(campaign_id)}


@router.patch("/admin/leads/{lead_id}/marketing-consent", dependencies=admin)
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


@router.get("/api/v1/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_page(token: str):
    """Confirm page. Opening the link does nothing by itself, so mail scanners cannot unsubscribe anyone."""
    if unsub.read_token(token) is None:
        return _plain_page("This link is not valid", "<p>It may be incomplete. Reply to the email and we will remove you.</p>", 404)
    return _plain_page(
        "Unsubscribe",
        '<p>Stop receiving promotional messages from this business?</p><form method="post"><button>Unsubscribe</button></form>',
    )


@router.post("/api/v1/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_do(token: str):
    """Performs the unsubscribe. Also serves mail apps' one-click unsubscribe (RFC 8058)."""
    result = await campaigns.unsubscribe(token)
    if result is None:
        return _plain_page("This link is not valid", "<p>Reply to the email and we will remove you.</p>", 404)
    return _plain_page(
        "You are unsubscribed",
        f"<p>{html.escape(result['tenant_name'])} will not send you promotional messages again.</p>",
    )


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
    if not _main().settings.email_drafts_enabled:
        raise HTTPException(status_code=503, detail="Email draft workflow is disabled")


@router.get("/admin/tenants/{slug}/email-drafts", dependencies=admin)
async def admin_email_drafts(slug: str, status: Literal["draft", "approved", "discarded", "all"] = "draft"):
    _email_feature_gate()
    tenant = await _main()._require_tenant(slug)
    return await email_drafts.list_drafts(tenant["id"], status)


@router.post("/admin/tenants/{slug}/email-drafts", dependencies=admin, status_code=201)
async def admin_email_draft_create(slug: str, body: EmailDraftCreate):
    _email_feature_gate()
    tenant = await _main()._require_tenant(slug)
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


@router.patch("/admin/tenants/{slug}/email-drafts/{draft_id}", dependencies=admin)
async def admin_email_draft_revise(slug: str, draft_id: int, body: EmailDraftRevision):
    _email_feature_gate()
    tenant = await _main()._require_tenant(slug)
    try:
        result = await email_drafts.revise(tenant["id"], draft_id, body.reply_body)
    except email_drafts.DraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Editable draft not found")
    return result


@router.post("/admin/tenants/{slug}/email-drafts/{draft_id}/discard", dependencies=admin)
async def admin_email_draft_discard(slug: str, draft_id: int):
    _email_feature_gate()
    tenant = await _main()._require_tenant(slug)
    result = await email_drafts.discard(tenant["id"], draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Editable draft not found")
    return result


@router.post("/admin/tenants/{slug}/email-drafts/{draft_id}/approve", dependencies=admin)
async def admin_email_draft_approve(slug: str, draft_id: int):
    _email_feature_gate()
    tenant = await _main()._require_tenant(slug)
    try:
        result = await email_drafts.approve(tenant["id"], draft_id)
    except email_drafts.DraftError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=409, detail="Draft already handled or does not exist")
    return result


# ------------------------------------------- inbound mailboxes, tracking, webhooks & suppressions
# Mailbox registration is operator-only; sending and receipt remain disabled by default.
class InboundMailbox(BaseModel):
    recipient: str = Field(min_length=3, max_length=320)
    enabled: bool = False


@router.post("/admin/tenants/{slug}/inbound-mailboxes", dependencies=admin)
async def register_inbound_mailbox(slug: str, body: InboundMailbox):
    tenant = await _main()._require_tenant(slug)
    try:
        await cloudflare_inbound.register_mailbox(tenant["id"], body.recipient, body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "enabled": body.enabled}


@router.post("/api/v1/inbound/cloudflare")
async def cloudflare_email_webhook(request: Request):
    return await cloudflare_inbound.handle(request)


@router.get("/l/{token}")
@router.get("/studio/l/{token}", include_in_schema=False)
async def tracked_link(token: str, request: Request):
    """Record an email link click, then send the visitor where the email pointed.

    The destination comes from the database, keyed by an unguessable token, so this cannot be
    turned into an open redirect. Repeat clicks return the same page and are recorded once: an
    open counter that inflates with every refresh is worse than no counter.
    """
    try:
        destination = await engagement.record_click(
            token, ip=(request.client.host if request.client else ""),
            user_agent=request.headers.get("user-agent", ""))
    except Exception:  # noqa: BLE001 - a tracking failure must not break the recipient's click
        log.warning("could not record click for link token %s", token[:12])
        destination = (await engagement.resolve(token) or {}).get("url") if token else None
    if not destination:
        raise HTTPException(404, "Unknown or expired link")
    return RedirectResponse(destination, status_code=302, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/webhooks/brevo")
async def brevo_email_webhook_status():
    """Human-friendly status for the POST-only webhook below.

    A browser click lands here, so it must not be a bare 405. This reveals nothing and
    processes nothing: Brevo is the only caller that may deliver events.
    """
    configured = bool(_main().get_settings().brevo_webhook_secret)
    return {"ok": configured, "endpoint": "brevo webhook", "method": "POST",
            "configured": configured,
            "usage": "POST delivery events here; configure the URL in Brevo > Transactional > Settings > Webhooks"}


@router.post("/webhooks/brevo")
async def brevo_email_webhook(request: Request, token: str = ""):
    """Brevo delivery-event webhook: bounces, blocks, complaints, unsubscribes.

    Brevo posts JSON, or form-encoded with the payload in a `json` field. The shared
    secret is compared in constant time; with no secret configured the endpoint stays
    closed, so an unauthenticated caller can never suppress a customer's address.
    """
    expected = _main().get_settings().brevo_webhook_secret
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
        if engagement.provider_kind(str(event.get("event") or "")):
            # Delivered/opened/click are not suppressions; they belong on the engagement timeline.
            results.append(await engagement.record_provider_event(event))
            continue
        results.append(await suppressions.record_event(event))
    return {"processed": len(results), "results": results}


class ManualSuppression(BaseModel):
    address: str = Field(max_length=320)
    reason: str = Field(default="blocked by owner", max_length=200)


@router.get("/owner/email-suppressions")
async def owner_suppressions(limit: int = 100, user: dict = Depends(owner_auth.current_user)):
    _email_feature_gate()
    return await suppressions.list_suppressions(user["tenant_id"], max(1, min(limit, 500)))


@router.post("/owner/email-suppressions", status_code=201)
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


@router.delete("/owner/email-suppressions/{address}")
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


@router.get("/admin/tenants/{slug}/email-suppressions", dependencies=admin)
async def admin_suppressions(slug: str, limit: int = 200):
    tenant = await _main()._require_tenant(slug)
    return await suppressions.list_suppressions(tenant["id"], max(1, min(limit, 500)))


# ------------------------------------------------------------------ owner saved replies & drafts
class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=8000)


@router.get("/owner/email-templates")
async def owner_templates(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, name, subject, body, updated_at FROM email_templates "
        "WHERE tenant_id=$1 ORDER BY name", user["tenant_id"])
    return [dict(row) for row in rows]


@router.post("/owner/email-templates", status_code=201)
async def owner_template_create(body: TemplateBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        row = await db.pool().fetchrow(
            "INSERT INTO email_templates (tenant_id, name, subject, body) VALUES ($1,$2,$3,$4) RETURNING *",
            user["tenant_id"], body.name.strip(), body.subject.strip(), body.body.rstrip())
    except Exception:
        raise HTTPException(409, "You already have a saved reply with that name")
    return dict(row)


@router.patch("/owner/email-templates/{template_id}")
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


@router.delete("/owner/email-templates/{template_id}")
async def owner_template_delete(template_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    gone = await db.pool().fetchval(
        "DELETE FROM email_templates WHERE id=$1::uuid AND tenant_id=$2 RETURNING id",
        template_id, user["tenant_id"])
    if gone is None:
        raise HTTPException(404, "Unknown saved reply")
    return {"deleted": True}


@router.get("/owner/email-drafts")
async def owner_drafts(
    status: Literal["draft", "approved", "discarded", "quarantined", "all"] = "draft",
    user: dict = Depends(owner_auth.current_user),
):
    _email_feature_gate()
    return await email_drafts.list_drafts(user["tenant_id"], status)


@router.patch("/owner/email-drafts/{draft_id}")
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


@router.post("/owner/email-drafts/{draft_id}/discard")
async def owner_discard_draft(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    row = await email_drafts.discard(user["tenant_id"], draft_id)
    if not row:
        raise HTTPException(404, "Draft not found")
    await inbound_policy.audit(user["tenant_id"], draft_id, "discarded", user.get("email", ""))
    return row


@router.post("/owner/email-drafts/{draft_id}/approve")
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


@router.post("/owner/email-drafts/{draft_id}/release")
async def owner_release_draft(draft_id: int, user: dict = Depends(owner_auth.current_user)):
    """Release a quarantined draft. Owner only: a second pair of eyes on high risk."""
    owner_auth.require_role(user, "owner")
    _email_feature_gate()
    row = await email_drafts.release(user["tenant_id"], draft_id)
    if not row:
        raise HTTPException(404, "No quarantined draft")
    await inbound_policy.audit(user["tenant_id"], draft_id, "released", user.get("email", ""))
    return row


@router.get("/owner/email-sender-rules")
async def owner_sender_rules(user: dict = Depends(owner_auth.current_user)):
    _email_feature_gate()
    return await inbound_policy.list_rules(user["tenant_id"])


@router.post("/owner/email-sender-rules", status_code=201)
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


@router.delete("/owner/email-sender-rules/{rule_id}")
async def owner_remove_sender_rule(rule_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    _email_feature_gate()
    if not await inbound_policy.remove_rule(user["tenant_id"], rule_id):
        raise HTTPException(404, "Rule not found")
    await inbound_policy.audit(user["tenant_id"], None, "rule_removed", user.get("email", ""),
                               {"rule_id": rule_id})
    return {"removed": True}


@router.get("/owner/email-engagement")
async def owner_email_engagement(limit: int = 100, user: dict = Depends(owner_auth.current_user)):
    _email_feature_gate()
    return await engagement.for_tenant(user["tenant_id"], limit)
