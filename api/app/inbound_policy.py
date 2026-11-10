"""Per-tenant inbound sender policy and audit trail.

Block wins over allow. A blocked sender is accepted and dropped (no backscatter
to a possibly spoofed address). An allowed sender still never triggers a model,
tool or send — it only avoids high-risk quarantine.
"""
import json
import re

from . import db

ADDRESS = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
DOMAIN = re.compile(r"^@[^\s@<>]+\.[^\s@<>]+$")
MAX_PATTERN = 320


def normalize(pattern: str) -> str:
    value = (pattern or "").strip().lower()
    if len(value) > MAX_PATTERN or not (ADDRESS.fullmatch(value) or DOMAIN.fullmatch(value)):
        raise ValueError("Use an email address or @domain")
    return value


def matches(pattern: str, sender: str) -> bool:
    address = (sender or "").strip().lower()
    if pattern.startswith("@"):
        return address.endswith(pattern)
    return address == pattern


async def rule_for(tenant_id, sender: str) -> str | None:
    rows = await db.pool().fetch(
        "SELECT pattern, action FROM inbound_sender_rules WHERE tenant_id=$1",
        tenant_id,
    )
    allowed = False
    for row in rows:
        if matches(row["pattern"], sender):
            if row["action"] == "block":
                return "block"
            allowed = True
    return "allow" if allowed else None


async def list_rules(tenant_id) -> list[dict]:
    rows = await db.pool().fetch(
        "SELECT id, pattern, action, created_by, created_at FROM inbound_sender_rules "
        "WHERE tenant_id=$1 ORDER BY id DESC", tenant_id)
    return [dict(row) for row in rows]


async def add_rule(tenant_id, pattern: str, action: str, actor: str) -> dict:
    if action not in ("allow", "block"):
        raise ValueError("Action must be allow or block")
    value = normalize(pattern)
    row = await db.pool().fetchrow(
        """INSERT INTO inbound_sender_rules(tenant_id,pattern,action,created_by)
           VALUES($1,$2,$3,$4)
           ON CONFLICT (tenant_id,pattern,action) DO UPDATE SET created_by=EXCLUDED.created_by
           RETURNING id,pattern,action,created_by,created_at""",
        tenant_id, value, action, actor,
    )
    return dict(row)


async def remove_rule(tenant_id, rule_id: int) -> bool:
    result = await db.pool().execute(
        "DELETE FROM inbound_sender_rules WHERE id=$1 AND tenant_id=$2",
        rule_id, tenant_id)
    return result == "DELETE 1"


async def audit(tenant_id, draft_id, action: str, actor: str, detail: dict | None = None) -> None:
    try:
        await db.pool().execute(
            "INSERT INTO inbound_audit(tenant_id,draft_id,action,actor,detail) "
            "VALUES($1,$2,$3,$4,$5::jsonb)",
            tenant_id, draft_id, action, actor, json.dumps(detail) if detail is not None else None)
    except Exception:
        # Auditing must never block mail handling; the draft row still holds risk data.
        pass


def defang(text: str) -> str:
    """Make links inert for display. The server never fetches any URL."""
    return (text or "").replace("https://", "hxxps://").replace("http://", "hxxp://")
