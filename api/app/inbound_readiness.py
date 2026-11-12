"""End-to-end readiness for the inbound email chain.

A tenant can look "connected" while every real message is refused. On 2026-11-12 the
live customer tenant had a reply address, a Cloudflare rule and a Worker route, but no
owner account and no `email_read` consent, so every inbound message was answered with
403 and the mail was only forwarded to the operator's inbox. Nothing in the product
noticed. This module walks the whole chain and reports each link, so onboarding (and a
cron/ops check) can refuse to call email "ready" until it actually is.

`evaluate()` is pure and unit-tested; `check()` gathers the facts from the database,
the Cloudflare API and the sidecar.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx

from . import channel_authorization, cloudflare_auth, db, tenants
from .config import get_settings

log = logging.getLogger("concierge.inbound_readiness")

# Every link that must hold before an inbound message can become a CRM draft.
ORDER = (
    "api_enabled",
    "owner_account",
    "consent",
    "reply_address",
    "mailbox",
    "worker_rule",
    "sidecar",
)

FIX = {
    "api_enabled": "Turn on inbound email for this deployment (INBOUND_CLOUDFLARE_ENABLED).",
    "owner_account": "Create the business owner's login; consent can only be granted by an owner.",
    "consent": "Sign in to the owner portal, open Permissions and authorise email read.",
    "reply_address": "Provision the tenant's reply address so Cloudflare has an address to route.",
    "mailbox": "Re-enable the tenant's inbound mailbox (cloudflare_inbound.register_mailbox).",
    "worker_rule": "Create or re-enable the Cloudflare Email Routing rule pointing at the Worker.",
    "sidecar": "Start the email-auth sidecar; without it mail is stored unverified at medium risk.",
}


def evaluate(facts: dict) -> dict:
    """Turn gathered facts into a verdict. Pure: no I/O, no exceptions on junk input."""
    def ok(name: str) -> bool:
        return {
            "api_enabled": bool(facts.get("api_enabled")),
            "owner_account": int(facts.get("owner_accounts") or 0) > 0,
            "consent": bool(facts.get("consent_authorized")),
            "reply_address": bool((facts.get("reply_address") or "").strip()),
            "mailbox": bool(facts.get("mailbox_enabled")),
            # "unknown" means we could not ask Cloudflare: not proof of failure, so it does
            # not block, but it is warned about below.
            "worker_rule": facts.get("worker_rule") != "missing",
            "sidecar": facts.get("sidecar_ok") is True,
        }[name]

    checks = {}
    for name in ORDER:
        passed = ok(name)
        detail = {
            "reply_address": facts.get("reply_address") or "",
            "worker_rule": facts.get("worker_rule") or "unknown",
            "sidecar": {True: "ok", False: "unreachable", None: "unknown"}[
                None if facts.get("sidecar_ok") is None else bool(facts.get("sidecar_ok"))
            ],
            "owner_accounts": int(facts.get("owner_accounts") or 0),
        }.get(name, "")
        checks[name] = {
            "ok": passed,
            "detail": detail,
            "fix": "" if passed else FIX[name],
        }

    blocked = [
        {"check": name, "message": FIX[name]}
        for name in ORDER
        if not checks[name]["ok"]
    ]
    # A blocked chain is a mail-dropping incident; a working chain that is only missing
    # the cryptographer still stores mail, so it is a warning rather than a blocker.
    warnings = []
    if facts.get("worker_rule") == "unknown":
        warnings.append({
            "check": "worker_rule",
            "message": "could not confirm the Cloudflare Email Routing rule; check once the API token is available",
        })
    unanswered = int(facts.get("rejected_24h") or 0)
    if unanswered:
        warnings.append({
            "check": "rejections",
            "message": f"{unanswered} inbound message(s) refused in the last 24h while this chain was incomplete",
        })
    return {
        "ok": not blocked,
        "blocked": blocked,
        "warnings": warnings,
        "checks": checks,
        "last_success_at": facts.get("last_success_at"),
        "rejected_24h": unanswered,
    }


async def _worker_rule(settings, reply_address: str) -> str:
    """enabled | missing | unknown — 'unknown' when we cannot ask Cloudflare."""
    if not (settings.cloudflare_zone_id and cloudflare_auth.configured(settings)):
        return "unknown"
    url = (f"https://api.cloudflare.com/client/v4/zones/{settings.cloudflare_zone_id}"
           "/email/routing/rules?per_page=50")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=cloudflare_auth.headers(settings))
        if response.status_code != 200:
            return "unknown"
        rules = (response.json() or {}).get("result") or []
    except (httpx.HTTPError, ValueError):
        return "unknown"
    for rule in rules:
        values = {(m or {}).get("value") for m in rule.get("matchers") or []}
        if reply_address in values:
            workers = [a for a in rule.get("actions") or [] if a.get("type") == "worker"]
            return "enabled" if rule.get("enabled") and workers else "missing"
    return "missing"


async def _sidecar_ok(settings) -> bool | None:
    if not settings.email_auth_url:
        return None
    url = settings.email_auth_url.rstrip("/")
    url = url[: -len("/verify")] + "/healthz" if url.endswith("/verify") else url + "/healthz"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def check(tenant_id) -> dict:
    """Gather live facts for one tenant and evaluate the whole chain."""
    settings = get_settings()
    tenant = await tenants.get_by_id(tenant_id)
    if tenant is None:
        raise ValueError("Tenant unavailable")

    owner_accounts = await db.pool().fetchval(
        "SELECT count(*) FROM tenant_users WHERE tenant_id=$1 AND active", tenant_id)
    consent = await channel_authorization.is_authorized(tenant_id, "email_read")
    reply_address = (tenant.get("reply_address") or "").strip()
    mailbox_enabled = bool(await db.pool().fetchval(
        "SELECT enabled FROM inbound_mailboxes WHERE tenant_id=$1 AND provider='cloudflare' LIMIT 1",
        tenant_id))
    last_success = await db.pool().fetchval(
        "SELECT max(created_at) FROM email_drafts WHERE tenant_id=$1", tenant_id)
    rejected = await db.pool().fetchval(
        "SELECT count(*) FROM inbound_audit WHERE tenant_id=$1 AND action='inbound_rejected' "
        "AND created_at > now() - interval '24 hours'", tenant_id)

    facts = {
        "api_enabled": bool(settings.inbound_cloudflare_enabled),
        "owner_accounts": owner_accounts or 0,
        "consent_authorized": bool(consent),
        "reply_address": reply_address,
        "mailbox_enabled": mailbox_enabled,
        "worker_rule": await _worker_rule(settings, reply_address) if reply_address else "missing",
        "sidecar_ok": await _sidecar_ok(settings),
        "last_success_at": last_success.isoformat() if last_success else None,
        "rejected_24h": int(rejected or 0),
    }
    verdict = evaluate(facts)
    verdict["slug"] = tenant["slug"]
    return verdict


async def check_all() -> dict:
    """Operator view: every tenant with a reply address, or that has ever had a draft."""
    rows = await db.pool().fetch(
        "SELECT id, slug FROM tenants WHERE reply_address IS NOT NULL "
        "OR EXISTS (SELECT 1 FROM email_drafts d WHERE d.tenant_id = tenants.id) ORDER BY slug")
    results = []
    for row in rows:
        try:
            results.append(await check(row["id"]))
        except Exception as exc:  # noqa: BLE001 - one broken tenant must not hide the rest
            log.exception("inbound readiness failed for %s", row["slug"])
            results.append({"slug": row["slug"], "ok": False, "blocked": [
                {"check": "inspection", "message": f"could not inspect tenant: {exc}"}]})
    return {
        "ok": all(r.get("ok") for r in results) if results else True,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tenants": results,
    }
