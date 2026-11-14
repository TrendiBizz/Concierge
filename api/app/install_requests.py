"""Put the chat on a customer's site without asking them to touch code.

The Setup step used to hand a tradesman a `<script>` tag and, if they looked unsure, suggest they
send it to their web person. For a builder that is a dead end — they have never edited their site
and they may not have a web person at all. Asking a customer to find a developer is a support
burden disguised as a feature.

So there are three doors, in the order a non-technical person can use them:

1. **We do it.** One button files a request; the operator installs it and marks it done. This is
   the default for anyone who does not want to touch their site.
2. **Their own dashboard.** A short, plain-language step for WordPress/Wix/Squarespace admins.
3. **A page we host.** No site access needed at all: a link and a QR code.
"""

from __future__ import annotations

import logging

from . import db, outbox

log = logging.getLogger("concierge.install_requests")

STATUSES = ("new", "contacted", "done", "cannot")
PLATFORMS = ("wordpress", "wix", "squarespace", "shopify", "webflow", "other", "unsure")


async def create(tenant_id, website: str, platform: str, contact_name: str, contact_phone: str,
                 note: str = "") -> dict:
    platform = platform if platform in PLATFORMS else "unsure"
    row = await db.pool().fetchrow(
        "INSERT INTO install_requests(tenant_id, website, platform, contact_name, contact_phone, note) "
        "VALUES($1,$2,$3,$4,$5,$6) RETURNING id, created_at",
        tenant_id, website.strip()[:300], platform, contact_name.strip()[:120],
        contact_phone.strip()[:40], note.strip()[:1000],
    )
    await _tell_the_operator(tenant_id, row["id"], website, platform, contact_name, contact_phone, note)
    return {"id": str(row["id"]), "status": "new", "created_at": row["created_at"]}


async def _tell_the_operator(tenant_id, request_id, website, platform, contact_name, contact_phone,
                             note) -> None:
    """Email the operator the one thing they need: whose site, on what, and how to reach them."""
    tenant = await db.pool().fetchrow(
        "SELECT name, slug, notify_email FROM tenants WHERE id=$1", tenant_id)
    if tenant is None:
        return
    to = await db.pool().fetchval(
        "SELECT coalesce(nullif(notify_email,''), 'admin@trendibizz.com') "
        "FROM tenants WHERE slug='trendi-support'") or "admin@trendibizz.com"
    body = f"""An install request came in.

Business: {tenant['name']} ({tenant['slug']})
Website:  {website}
Platform: {platform}
Contact:  {contact_name or '(none given)'} {contact_phone or ''}
Note:     {note or '(none)'}

Install it for them, or reply to say what you need. When it is done, mark request {request_id} done:
POST /admin/install-requests/{request_id}/done
"""
    try:
        await outbox.enqueue(tenant_id, "owner_alert", "email", to, body,
                             subject=f"Install request — {tenant['name']}",
                             dedupe_key=f"install-request:{request_id}")
    except Exception:  # noqa: BLE001 - the request is recorded; the operator list still shows it
        log.exception("install request %s could not be emailed", request_id)


async def for_tenant(tenant_id) -> list[dict]:
    rows = await db.pool().fetch(
        "SELECT id, website, platform, contact_name, contact_phone, note, status, created_at, "
        "handled_at FROM install_requests WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 20",
        tenant_id)
    return [_json(r) for r in rows]


async def list_all(status: str = "") -> list[dict]:
    sql = ("SELECT r.*, t.name AS business, t.slug FROM install_requests r "
           "JOIN tenants t ON t.id=r.tenant_id")
    args = []
    if status in STATUSES:
        sql += " WHERE r.status=$1"
        args.append(status)
    sql += " ORDER BY r.created_at DESC LIMIT 100"
    return [_json(r) for r in await db.pool().fetch(sql, *args)]


async def set_status(request_id, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError("Unknown status")
    row = await db.pool().fetchrow(
        "UPDATE install_requests SET status=$2, handled_at=CASE WHEN $2 IN ('done','cannot') "
        "THEN now() ELSE handled_at END WHERE id=$1 RETURNING id, status", request_id, status)
    if row is None:
        raise ValueError("No such request")
    return {"id": str(row["id"]), "status": row["status"]}


def _json(row) -> dict:
    item = dict(row)
    for key in ("id", "tenant_id"):
        if key in item:
            item[key] = str(item[key])
    for key, value in list(item.items()):
        if hasattr(value, "isoformat"):
            item[key] = value.isoformat()
    return item
