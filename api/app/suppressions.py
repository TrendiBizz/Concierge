"""Outbound-email suppression list.

An address lands here when a bounce says it is dead, the provider blocks it, a
recipient complains, or an operator blocks it deliberately. Outbound delivery in
`outbox._deliver` refuses a suppressed address, so a dead mailbox is never retried
and reputation does not erode.

Two entry points feed it:
  * `record_dsn`   — a delivery status notification arrived through our own inbox
                     (Cloudflare Worker) and was parsed by `bounces.parse`;
  * `record_event` — Brevo posted a webhook event (hard_bounce/blocked/spam/...).

Both are idempotent: the same bounce twice keeps one row.
"""
import json
import logging
import re

from . import db, inbound_policy

log = logging.getLogger("concierge.suppressions")

ADDRESS = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
MAX_ADDRESS = 320

HARD_EVENTS = {"hard_bounce", "hardbounce", "invalid_email", "invalid", "blocked", "spam", "complaint"}
SOFT_EVENTS = {"soft_bounce", "softbounce", "deferred", "delay"}


def normalize(address: str) -> str:
    value = (address or "").strip().strip("<>").lower()
    if len(value) > MAX_ADDRESS or not ADDRESS.fullmatch(value):
        raise ValueError("Invalid email address")
    return value


async def add(tenant_id, address: str, reason: str, source: str, detail: dict | None = None) -> bool:
    """Suppress one address for one tenant. Returns True when a new row was created."""
    value = normalize(address)
    result = await db.pool().execute(
        """INSERT INTO email_suppressions(tenant_id,address,reason,source,detail)
           VALUES($1,$2,$3,$4,$5::jsonb)
           ON CONFLICT (tenant_id,address) DO UPDATE SET
             reason=EXCLUDED.reason, source=EXCLUDED.source, detail=EXCLUDED.detail""",
        tenant_id, value, (reason or "")[:200], (source or "")[:60],
        json.dumps(detail or {}),
    )
    await inbound_policy.audit(
        tenant_id, None, "address_suppressed", source or "system",
        {"address": value, "reason": (reason or "")[:200], **(detail or {})})
    return result == "INSERT 0 1"


async def is_suppressed(tenant_id, address: str) -> bool:
    try:
        value = normalize(address)
    except ValueError:
        return False
    found = await db.pool().fetchval(
        "SELECT 1 FROM email_suppressions WHERE tenant_id=$1 AND address=$2", tenant_id, value)
    return bool(found)


async def remove(tenant_id, address: str) -> bool:
    value = normalize(address)
    result = await db.pool().execute(
        "DELETE FROM email_suppressions WHERE tenant_id=$1 AND address=$2", tenant_id, value)
    removed = result == "DELETE 1"
    if removed:
        await inbound_policy.audit(tenant_id, None, "suppression_removed", "owner", {"address": value})
    return removed


async def list_suppressions(tenant_id, limit: int = 100) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT address,reason,source,detail,created_at FROM email_suppressions
           WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2""",
        tenant_id, limit)
    return [dict(row) for row in rows]


async def _close_outbox(tenant_id, address: str, message_id: str, reason: str) -> int:
    """Stop retrying the message(s) that could not be delivered.

    Match on the Message-ID when the report carries one (precise, even for a
    forwarded bounce) and on the recipient otherwise. Only rows that are not
    already terminal are touched.
    """
    query = """
        UPDATE outbox SET status='failed', last_error=$3
        WHERE tenant_id=$1
          AND ($2 = '' OR message_id=$2 OR lower(to_addr)=lower($4))
          AND status IN ('pending','sending','sent')
        """
    result = await db.pool().execute(query, tenant_id, message_id or "", reason[:500], address)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def record_dsn(tenant_id, parsed: dict) -> dict:
    """Apply a parsed delivery report: suppress hard bounces, close the outbox row."""
    address = (parsed or {}).get("address") or ""
    status = (parsed or {}).get("status") or ""
    hard = bool((parsed or {}).get("hard"))
    message_id = (parsed or {}).get("original_message_id") or ""
    if not address:
        return {"suppressed": False, "closed": 0}
    closed = await _close_outbox(
        tenant_id, address, message_id,
        f"bounce {status or 'unknown'}: {(parsed or {}).get('diagnostic') or ''}",
    )
    suppressed = False
    if hard:
        suppressed = await add(
            tenant_id, address, f"hard bounce {status}".strip(),
            "dsn", {"status": status, "diagnostic": (parsed or {}).get("diagnostic") or ""},
        )
    return {"suppressed": suppressed, "closed": closed}


async def record_event(event: dict) -> dict:
    """Apply a Brevo-style provider event. Returns what it changed."""
    name = str((event or {}).get("event") or "").strip().lower()
    address = str((event or {}).get("email") or "")
    message_id = str((event or {}).get("message-id") or "")
    tenant_id = (event or {}).get("tenant_id")
    if not address or not tenant_id:
        return {"ignored": "missing address or tenant"}
    try:
        address = normalize(address)
    except ValueError:
        return {"ignored": "invalid address"}
    reason = str((event or {}).get("reason") or name)[:300]
    if name in HARD_EVENTS:
        closed = await _close_outbox(tenant_id, address, message_id, f"{name}: {reason}")
        created = await add(tenant_id, address, name, "brevo",
                            {"reason": reason, "message_id": message_id[:500]})
        return {"suppressed": created, "closed": closed}
    if name in SOFT_EVENTS:
        # A deferral is not a dead mailbox; record it, do not suppress.
        await inbound_policy.audit(tenant_id, None, "delivery_deferred", "brevo",
                                   {"address": address, "reason": reason})
        return {"deferred": True}
    if name in ("unsubscribed", "unsub"):
        await inbound_policy.audit(tenant_id, None, "unsubscribed_provider", "brevo",
                                   {"address": address})
        return {"unsubscribed": True}
    return {"ignored": name or "unknown event"}
