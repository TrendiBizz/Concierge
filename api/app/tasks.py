"""To-dos for the business owner.

Two kinds of to-do share one list:
  - manual: added by the owner in the dashboard.
  - follow_up: created automatically for every new lead ("Follow up: Hana"), one per lead. It is due in an
    hour for a hot lead (or the client's response target if one is set) and at 9am the next morning for
    everyone else. It completes itself the moment the lead moves out of 'new', so the list only ever shows
    work that is still undone.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db

STATUSES = ("open", "done")
EDITABLE = {"title", "notes", "due_at", "status"}


class TaskError(ValueError):
    pass


def default_follow_up_due(tenant: dict, lead: dict, now: datetime | None = None) -> datetime:
    """When a new lead's follow-up should happen."""
    now = now or datetime.now(timezone.utc)
    if lead.get("score_label") == "hot":
        return now + timedelta(minutes=int(tenant.get("sla_minutes") or 60))
    tz = ZoneInfo(tenant.get("timezone") or "UTC")
    local = now.astimezone(tz)
    nine = datetime.combine(local.date(), time(9), tzinfo=tz)
    if local >= nine:
        nine += timedelta(days=1)
    return nine.astimezone(timezone.utc)


def clean_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise TaskError("A to-do needs a title")
    if len(title) > 200:
        raise TaskError("Title is too long (200 characters max)")
    return title


async def create(
    tenant_id, title: str, notes: str = "", due_at: datetime | None = None,
    source: str = "manual", kind: str = "manual", lead_id=None,
    case_id=None, message_key: str | None = None,
) -> dict:
    row = await db.pool().fetchrow(
        "INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, case_id, message_key) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *",
        tenant_id, lead_id, clean_title(title), (notes or "")[:2000], due_at, kind, source,
        case_id, message_key,
    )
    return dict(row)


async def create_follow_up(tenant: dict, lead: dict, message_key: str | None = None) -> dict | None:
    """The automatic follow-up for a new lead, or for one new inbound message.

    Two uniqueness rules, and the difference matters:
      - with message_key: one follow-up per (case, message), so a customer who writes again gets
        fresh work instead of being silently ignored after the first contact;
      - without it: the original one-per-lead rule, so existing callers that carry no message
        identity -- and any replayed call -- cannot create duplicates.

    Returns None when a matching follow-up already exists.
    """
    who = lead.get("name") or lead.get("phone") or lead.get("email") or "new lead"
    notes = (lead.get("message") or "")[:300]
    due = default_follow_up_due(tenant, lead)
    if message_key:
        row = await db.pool().fetchrow(
            "INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, case_id, message_key) "
            "VALUES ($1, $2, $3, $4, $5, 'follow_up', 'system', $6, $7) "
            "ON CONFLICT (case_id, message_key) WHERE kind = 'follow_up' AND message_key IS NOT NULL "
            "DO NOTHING RETURNING *",
            tenant["id"], lead["id"], f"Follow up: {who}"[:200], notes, due,
            lead.get("case_id"), message_key[:200],
        )
    else:
        row = await db.pool().fetchrow(
            "INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, case_id) "
            "VALUES ($1, $2, $3, $4, $5, 'follow_up', 'system', $6) "
            "ON CONFLICT (lead_id) WHERE kind = 'follow_up' DO NOTHING RETURNING *",
            tenant["id"], lead["id"], f"Follow up: {who}"[:200], notes, due, lead.get("case_id"),
        )
    return dict(row) if row else None


async def set_follow_up_due(lead: dict, due_at: datetime) -> dict:
    """Move (or recreate) a lead's follow-up to a date the owner chose. Reopens it if it was done."""
    who = lead.get("name") or lead.get("phone") or lead.get("email") or "lead"
    row = await db.pool().fetchrow(
        "INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source) "
        "VALUES ($1, $2, $3, $4, $5, 'follow_up', 'manual') "
        "ON CONFLICT (lead_id) WHERE kind = 'follow_up' "
        "DO UPDATE SET due_at = EXCLUDED.due_at, status = 'open', completed_at = NULL RETURNING *",
        lead["tenant_id"], lead["id"], f"Follow up: {who}"[:200], (lead.get("message") or "")[:300], due_at,
    )
    return dict(row)


async def complete_for_lead(lead_id) -> int:
    result = await db.pool().execute(
        "UPDATE tasks SET status = 'done', completed_at = now() "
        "WHERE lead_id = $1 AND kind = 'follow_up' AND status = 'open'", lead_id)
    return int(result.split()[-1])


async def list_tasks(tenant_id, status: str = "open", limit: int = 200) -> list[dict]:
    where = "" if status == "all" else "AND t.status = $2"
    args = [tenant_id] if status == "all" else [tenant_id, status]
    order = ("t.due_at NULLS LAST, t.created_at" if status == "open"
             else "COALESCE(t.completed_at, t.created_at) DESC")
    rows = await db.pool().fetch(
        f"""
        SELECT t.*, l.name AS lead_name, l.score_label AS lead_label
        FROM tasks t LEFT JOIN leads l ON l.id = t.lead_id
        WHERE t.tenant_id = $1 {where} ORDER BY {order} LIMIT {int(min(max(limit, 1), 500))}
        """,
        *args,
    )
    return [dict(r) for r in rows]


async def get(task_id: int) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
    return dict(row) if row else None


async def update(task_id: int, fields: dict) -> dict | None:
    data = {k: v for k, v in fields.items() if k in EDITABLE}
    if "title" in data:
        data["title"] = clean_title(data["title"])
    if "status" in data and data["status"] not in STATUSES:
        raise TaskError("status must be open or done")
    if not data:
        raise TaskError("Nothing to update")
    parts, values = [], []
    for i, (col, value) in enumerate(data.items(), start=2):
        parts.append(f"{col} = ${i}")
        values.append(value)
    if "status" in data:
        parts.append("completed_at = " + ("now()" if data["status"] == "done" else "NULL"))
    row = await db.pool().fetchrow(
        f"UPDATE tasks SET {', '.join(parts)} WHERE id = $1 RETURNING *", task_id, *values)
    return dict(row) if row else None


async def delete(task_id: int) -> bool:
    return (await db.pool().execute("DELETE FROM tasks WHERE id = $1", task_id)).endswith("1")


async def overdue_count(tenant_id) -> int:
    return int(await db.pool().fetchval(
        "SELECT count(*) FROM tasks WHERE tenant_id = $1 AND status = 'open' AND due_at < now()", tenant_id) or 0)
