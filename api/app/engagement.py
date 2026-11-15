"""Knowing that an email was acted on, without pretending an open is a read.

A 1x1 pixel is the obvious way to see whether an email was opened, and it is the wrong one: Apple
Mail Privacy Protection and Gmail's image proxy fetch it whether or not a person reads the message,
and corporate mail scanners fetch every image the moment mail arrives. So a pixel measures delivery
infrastructure, not a human.

This module records the two things that do mean something:

* **A click** — the recipient chose to follow a link. `email_link` stores the destination server
  side, so the redirect can never be pointed at an arbitrary URL and the same link reported twice
  cannot inflate the count.
* **A provider event** — Brevo reports `delivered` / `opened` / `click` for mail we sent. Opens are
  labelled as the soft signal they are and stored with the message id, deduped once per message.

Nothing here runs unless `TRACKED_LINKS_BASE` is configured, because rewriting a customer's links
through a tracking host is a decision an operator has to make deliberately.
"""

from __future__ import annotations

import html as html_lib
import re
import secrets
from urllib.parse import urlsplit

from . import db
from .config import get_settings

# Only these get a tracked HTML alternative. Transactional mail to customers stays plain text.
TRACKED_KINDS = frozenset({"owner_alert", "campaign", "email_secretary_reply"})
MAX_LINKS_PER_MESSAGE = 40
PROVIDER_KINDS = {"delivered": "delivered", "opened": "open", "open": "open", "click": "click"}

# The edge proxy for concierge.trendibizz.com forwards /studio/* and /webhooks/* to the API and
# answers everything else itself, so a tracked link has to live under /studio. Verified on the box
# on 2026-11-15: https://concierge.trendibizz.com/l/<token> returned the edge's empty 404 while
# /studio/l/<token> reaches the redirect below.
TRACKED_PATH = "/studio/l"

URL_RE = re.compile(r"https?://[^\s<>\"']+")
TRAILING = ").,;:!?]'\"»"


def tracking_base() -> str:
    """The public origin links are rewritten through, or "" when tracking is off."""
    return (get_settings().tracked_links_base or "").strip().rstrip("/")


def enabled_for(kind: str) -> bool:
    return bool(tracking_base()) and kind in TRACKED_KINDS


def provider_kind(name: str) -> str | None:
    """Map a provider event name to what we record, or None when it is not ours to record."""
    return PROVIDER_KINDS.get((name or "").strip().lower())


def clean_url(url: str) -> str | None:
    """A link we are willing to redirect to: absolute http(s), no credentials, no fragment games."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    return url


async def remember_link(outbox_id: int, tenant_id, url: str) -> str | None:
    """Store a destination and return its token. Re-uses the stored token for a repeat link."""
    safe = clean_url(url)
    if not safe or not outbox_id:
        return None
    existing = await db.pool().fetchval(
        "SELECT token FROM email_link WHERE outbox_id=$1 AND url=$2", outbox_id, safe)
    if existing:
        return existing
    token = secrets.token_urlsafe(9)
    await db.pool().execute(
        "INSERT INTO email_link (token, outbox_id, tenant_id, url) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (token) DO NOTHING", token, outbox_id, tenant_id, safe)
    return token


async def resolve(token: str) -> dict | None:
    return await db.pool().fetchrow(
        "SELECT token, outbox_id, tenant_id, url FROM email_link WHERE token=$1", token)


async def record_click(token: str, ip: str = "", user_agent: str = "") -> str | None:
    """Record the first click on a link and return its destination. Re-clicks do not double count."""
    row = await resolve(token)
    if row is None:
        return None
    await db.pool().execute(
        "INSERT INTO email_engagement (tenant_id, outbox_id, token, kind, url, ip, user_agent) "
        "VALUES ($1,$2,$3,'click',$4,$5,$6) ON CONFLICT (token, kind) DO NOTHING",
        row["tenant_id"], row["outbox_id"], token, row["url"], ip[:64], user_agent[:400])
    return row["url"]


async def record_provider_event(event: dict) -> dict:
    """Record a Brevo delivered/opened/click event against the outbox row it belongs to."""
    kind = provider_kind(str((event or {}).get("event") or ""))
    if kind is None:
        return {"ignored": "not an engagement event"}
    message_id = str((event or {}).get("message-id") or "")
    address = str((event or {}).get("email") or "")
    tenant_id = (event or {}).get("tenant_id")
    if not message_id or not tenant_id:
        return {"ignored": "missing message id or tenant"}
    outbox_id = await db.pool().fetchval(
        "SELECT id FROM outbox WHERE message_id=$1 ORDER BY id DESC LIMIT 1", message_id)
    await db.pool().execute(
        "INSERT INTO email_engagement (tenant_id, outbox_id, kind, message_id, to_addr, url) "
        "VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING",
        tenant_id, outbox_id, kind, message_id[:500], address or None,
        (str(event.get("link") or "") or None))
    return {"recorded": kind}


async def render_html(outbox_id: int, tenant_id, text: str) -> str:
    """Turn a plain-text body into a tracked HTML alternative.

    Called only from the outbox send path, so the cost is one insert per unique link per message.
    """
    base = tracking_base()
    seen: dict[str, str] = {}
    budget = MAX_LINKS_PER_MESSAGE
    pieces: list[str] = []
    cursor = 0
    for match in URL_RE.finditer(text):
        raw = match.group(0)
        tail = ""
        while raw and raw[-1] in TRAILING:
            tail = raw[-1] + tail
            raw = raw[:-1]
        token = None
        if budget > 0:
            key = clean_url(raw)
            if key:
                token = seen.get(key)
                if token is None:
                    token = await remember_link(outbox_id, tenant_id, key)
                    if token:
                        seen[key] = token
                        budget -= 1
        pieces.append(html_lib.escape(text[cursor:match.start()]))
        label = html_lib.escape(raw)
        if token:
            href = f"{base}{TRACKED_PATH}/{token}"
            pieces.append(f'<a href="{html_lib.escape(href)}">{label}</a>')
        else:
            pieces.append(label)
        pieces.append(html_lib.escape(tail))
        cursor = match.start() + len(match.group(0))
    pieces.append(html_lib.escape(text[cursor:]))
    body = "".join(pieces).replace("\r\n", "\n").replace("\n", "<br>\n")
    return ("<!doctype html><html><body style=\"font-family:-apple-system,Segoe UI,Helvetica,Arial,"
            "sans-serif;font-size:16px;line-height:1.5;color:#1c1c1e\">" + f"<p>{body}</p>" "</body></html>")


async def for_tenant(tenant_id, limit: int = 100) -> list[dict]:
    """Recent engagement for the portal timeline: who clicked what, and which messages were opened."""
    rows = await db.pool().fetch(
        "SELECT kind, token, message_id, to_addr, url, created_at FROM email_engagement "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2", tenant_id, max(1, min(limit, 500)))
    return [dict(r) for r in rows]
