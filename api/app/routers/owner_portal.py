"""Owner portal, auth/session, team management, push notifications, onboarding, knowledge base,
channel authorizations, pause switch, install requests, and release notice routes.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import asyncio
import logging
import sys
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import (
    brand_from_site, channel_authorization, channel_health, db, inbound_policy,
    inbound_readiness, ingest, install_requests, owner_auth, owner_knowledge,
    owner_onboarding, provider_readiness, releases, reply_address, tenant_pause,
    tenants, webpush,
)

log = logging.getLogger("concierge")
router = APIRouter()


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


class OwnerInvite(BaseModel):
    email: str = Field(max_length=320)
    role: Literal["viewer", "editor", "owner"] = "viewer"
    # Opt-in: email the single-use link to the invitee. Off by default so the operator can still
    # deliver it over a channel they have verified themselves.
    send_email: bool = False


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


@router.get("/owner/locale")
async def owner_locale(request: Request):
    country = (request.headers.get("cf-ipcountry") or "").upper()
    return {"country": country, "locale": COUNTRY_LOCALE.get(country, "en"),
            "supported": ["en", "fr-FR", "es-ES", "de-DE", "pt-BR", "zh-CN", "ja-JP", "ko-KR", "ar-SA", "nl-NL", "it-IT", "pl-PL"]}


@router.get("/owner/me")
async def owner_me(user: dict = Depends(owner_auth.current_user)):
    return {"email": user["email"], "role": user["role"], "tenant": user["slug"]}


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscribe(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000)
    keys: PushKeys
    user_agent: str = Field(default="", max_length=300)


class PushEndpoint(BaseModel):
    endpoint: str = Field(min_length=20, max_length=1000)


@router.get("/owner/sw.js", include_in_schema=False)
async def owner_service_worker():
    """The owner page's alert worker. Served under /owner/ (the only prefix the public proxy forwards)
    and allowed to control /owner-ui, which a worker at this path could not otherwise do."""
    return FileResponse(_main().STATIC_DIR / "owner-sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
                                 "Service-Worker-Allowed": "/owner-ui"})


@router.get("/owner/push/key")
async def owner_push_key(user: dict = Depends(owner_auth.current_user)):
    if not webpush.configured():
        raise HTTPException(503, "Phone alerts are not set up on this server yet")
    return {"public_key": _main().settings.vapid_public_key}


@router.post("/owner/push/subscribe", status_code=201)
async def owner_push_subscribe(body: PushSubscribe, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not webpush.allowed_endpoint(body.endpoint):
        raise HTTPException(400, "That device's push service is not supported")
    await webpush.save(user["tenant_id"], body.endpoint, body.keys.p256dh, body.keys.auth, body.user_agent)
    return {"subscribed": True}


@router.post("/owner/push/unsubscribe")
async def owner_push_unsubscribe(body: PushEndpoint, user: dict = Depends(owner_auth.current_user)):
    await webpush.remove(user["tenant_id"], body.endpoint)
    return {"subscribed": False}


@router.post("/owner/push/test", status_code=202)
async def owner_push_test(body: PushEndpoint, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await webpush.send_test(user["tenant_id"], body.endpoint)


@router.get("/owner/channel-health")
async def owner_channel_health(user: dict = Depends(owner_auth.current_user)):
    """Plain status of email alerts, the SMS phone and voice calls for this business."""
    return await channel_health.channel_report(user["tenant_id"])


@router.post("/owner/alerts/test", status_code=202)
async def owner_test_alert(user: dict = Depends(owner_auth.current_user)):
    """Send a test alert to the owner's own email and mobile so they can confirm it arrives."""
    owner_auth.require_role(user, "owner")
    tenant = await _main()._require_tenant(user["slug"])
    return await channel_health.send_test_alert(tenant)


class InstallRequest(BaseModel):
    website: str = Field(default="", max_length=300)
    platform: str = Field(default="unsure", max_length=30)
    contact_name: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=1000)


@router.post("/owner/install-request")
async def owner_install_request(body: InstallRequest, user: dict = Depends(owner_auth.current_user)):
    """The customer asks us to put the chat on their site. No code, no third party."""
    return await install_requests.create(
        user["tenant_id"], body.website, body.platform, body.contact_name, body.contact_phone,
        body.note)


@router.get("/owner/install-requests")
async def owner_install_requests(user: dict = Depends(owner_auth.current_user)):
    return await install_requests.for_tenant(user["tenant_id"])


@router.get("/version")
@router.get("/owner/version")  # the public edge only forwards /owner/*, so the Studio footer reads this one
async def public_version():
    """Which release is live. Public on purpose: it names a number, nothing about any business."""
    return {"version": releases.CURRENT_VERSION, "label": releases.label()}


@router.get("/owner/release")
async def owner_release(user: dict = Depends(owner_auth.current_user)):
    seen = await db.pool().fetchval("SELECT last_seen_version FROM tenant_users WHERE id=$1", user["id"])
    return releases.notice(int(seen or 0))


@router.post("/owner/release/seen")
async def owner_release_seen(user: dict = Depends(owner_auth.current_user)):
    await releases.mark_seen(user["id"])
    return {"seen": releases.CURRENT_VERSION}


@router.get("/owner/provider-readiness")
async def owner_provider_readiness(user: dict = Depends(owner_auth.current_user)):
    """What is blocking each provider, and which steps need a person rather than a deployment.

    Reads configuration only and changes nothing. A step marked ready means the software side is
    satisfied; it is NOT a claim that the provider has accepted anything, which only the provider
    can confirm.
    """
    owner_auth.require_role(user, "owner")
    return provider_readiness.report()


@router.post("/owner/auth/logout")
async def owner_logout(request: Request, user: dict = Depends(owner_auth.current_user)):
    await owner_auth.logout(request.headers["authorization"].partition(" ")[2])
    return {"ok": True}


@router.get("/owner/onboarding")
async def owner_onboarding_overview(user: dict = Depends(owner_auth.current_user)):
    try:
        return await owner_onboarding.overview(user["tenant_id"])
    except ValueError:
        raise HTTPException(404, "Business not found") from None


@router.patch("/owner/onboarding/profile")
async def owner_onboarding_update(
    body: owner_onboarding.OwnerBusinessProfile,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    try:
        return await owner_onboarding.update_profile(user["slug"], body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/owner/onboarding/authorizations")
async def owner_channel_authorizations(user: dict = Depends(owner_auth.current_user)):
    return await channel_authorization.authorizations(user["tenant_id"])


@router.post("/owner/knowledge/import-website")
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


@router.get("/owner/knowledge")
async def owner_knowledge_list(user: dict = Depends(owner_auth.current_user)):
    return await owner_knowledge.documents(user["tenant_id"])


@router.post("/owner/knowledge", status_code=201)
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


@router.delete("/owner/knowledge/{document_id}")
async def owner_knowledge_delete(document_id: str,
                                 user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await owner_knowledge.remove(user["tenant_id"], document_id):
        raise HTTPException(404, "Business document not found")
    return {"ok": True}


@router.get("/owner/onboarding/brand-suggestion")
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


@router.get("/owner/onboarding/install-check")
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


@router.get("/owner/onboarding/inbound-readiness")
async def owner_inbound_readiness(user: dict = Depends(owner_auth.current_user)):
    """Whole-chain check for this tenant's inbound email. Onboarding must not claim
    email is ready unless every link is green: a missing consent row drops real mail."""
    return await inbound_readiness.check(user["tenant_id"])


@router.get("/owner/inbound-audit")
async def owner_inbound_audit(limit: int = 50, user: dict = Depends(owner_auth.current_user)):
    """Refused and blocked inbound mail for this tenant: who, what and why.

    A count alone told the owner that mail was lost but never which customer sent it.
    """
    _main()._email_feature_gate()
    return await inbound_policy.recent(user["tenant_id"], max(1, min(limit, 200)))


@router.get("/owner/onboarding/authorization-audit")
async def owner_authorization_audit(
    limit: int = 50, user: dict = Depends(owner_auth.current_user),
):
    """Who granted or revoked each channel, and how. The database writes these rows, so a
    direct-SQL change is recorded too (actor_kind='direct') instead of vanishing."""
    return await channel_authorization.audit_log(user["tenant_id"], max(1, min(limit, 200)))


class PauseRequest(BaseModel):
    paused: bool


@router.get("/owner/pause")
async def owner_pause_state(user: dict = Depends(owner_auth.current_user)):
    """Always readable, so the Studio can show the switch without hunting for a permission."""
    return await tenant_pause.state(user["tenant_id"])


@router.post("/owner/pause")
async def owner_set_pause(body: PauseRequest, user: dict = Depends(owner_auth.current_user)):
    """Stop or resume Concierge for this business only.

    Never the operator's deployment-wide kill switch (flood_guard): one customer must not be able
    to silence another.
    """
    owner_auth.require_role(user, "owner")
    return await tenant_pause.set_paused(
        user["tenant_id"], body.paused, user.get("email") or "owner")


@router.post("/owner/onboarding/authorizations")
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


@router.post("/owner/onboarding/email-auto-reply")
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


@router.post("/owner/onboarding/native-booking")
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


@router.get("/owner/onboarding/readiness")
async def owner_channel_readiness(user: dict = Depends(owner_auth.current_user)):
    status = await owner_onboarding.overview(user["tenant_id"])
    declarations = await channel_authorization.authorizations(user["tenant_id"])
    settings = _main().get_settings()
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


@router.post("/owner/invitations", status_code=201)
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


@router.get("/owner/team")
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


@router.patch("/owner/team/{user_id}")
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


@router.post("/owner/team/{user_id}/deactivate")
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


@router.post("/owner/team/{user_id}/reactivate")
async def owner_team_reactivate(user_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    target = await _team_member(user["tenant_id"], user_id)
    await db.pool().execute(
        "UPDATE tenant_users SET active=true WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], user_id)
    return {"id": str(user_id), "active": True, "email": target["email"]}
