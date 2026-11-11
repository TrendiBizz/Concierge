"""Per-tenant reply address for owner notifications.

Owner alerts are sent to the business owner. Their Reply-To is a tenant-specific
address on our domain, routed by Cloudflare Email Routing back into the same
tenant's CRM, so a reply never lands in another client's inbox.
"""
import logging

import httpx

from . import db
from .config import get_settings

log = logging.getLogger("concierge.reply_address")


async def _cloudflare_rule(tenant: dict) -> None:
    settings = get_settings()
    if not (settings.cloudflare_api_key and settings.cloudflare_email and settings.cloudflare_zone_id):
        raise ValueError("Cloudflare Email Routing is not configured for reply addresses")
    base = f"https://api.cloudflare.com/client/v4/zones/{settings.cloudflare_zone_id}/email/routing/rules"
    headers = {"X-Auth-Key": settings.cloudflare_api_key, "X-Auth-Email": settings.cloudflare_email}
    address = tenant["reply_address"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        existing = await client.get(base, headers=headers)
        existing.raise_for_status()
        for rule in existing.json().get("result", []):
            for matcher in rule.get("matchers", []):
                if matcher.get("value") == address:
                    return
        response = await client.post(base, headers=headers, json={
            "name": f"reply {tenant['slug']}",
            "enabled": True,
            "matchers": [{"type": "literal", "field": "to", "value": address}],
            "actions": [{"type": "worker", "value": [settings.cloudflare_worker_name]}],
        })
        if response.status_code >= 300:
            raise ValueError(f"Cloudflare rejected the reply route: {response.text[:200]}")


async def ensure(tenant: dict) -> dict:
    """Give the tenant a reply address, mailbox row and Cloudflare route."""
    if tenant.get("reply_address"):
        await db.pool().execute(
            """INSERT INTO inbound_mailboxes(recipient,tenant_id,provider,enabled)
               VALUES($1,$2,'cloudflare',true)
               ON CONFLICT(recipient) DO UPDATE SET enabled=true
               WHERE inbound_mailboxes.tenant_id=EXCLUDED.tenant_id""",
            tenant["reply_address"], tenant["id"])
        await _cloudflare_rule(tenant)
        return tenant
    import secrets
    address = "reply-" + secrets.token_hex(12) + "@" + get_settings().reply_domain
    row = await db.pool().fetchrow(
        "UPDATE tenants SET reply_address=$2 WHERE id=$1 RETURNING *", tenant["id"], address)
    updated = dict(row)
    await db.pool().execute(
        """INSERT INTO inbound_mailboxes(recipient,tenant_id,provider,enabled)
           VALUES($1,$2,'cloudflare',true)
           ON CONFLICT(recipient) DO NOTHING""",
        address, tenant["id"])
    await _cloudflare_rule(updated)
    log.info("reply address ready for %s", tenant["slug"])
    return updated
