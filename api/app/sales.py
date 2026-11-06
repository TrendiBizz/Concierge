"""Sales management: a pipeline over the leads, stage history, a weighted forecast and a weekly summary.

Stages are the lead statuses already used everywhere: new -> contacted -> booked -> won / lost. Every move
is recorded (lead_events), a lead's follow-up to-do completes when it leaves 'new', and won / lost stamp
their date (lost also keeps a reason). Open deals without their own value use the client's average lead
value, and the forecast weights each open stage by how often leads at that stage tend to close.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, outbox, sla, tasks
from .config import get_settings
from .contact import is_email

log = logging.getLogger("concierge.sales")

STAGES = ("new", "contacted", "booked", "won", "lost")
OPEN_STAGES = ("new", "contacted", "booked")
# How likely a lead at each stage is to be won. A starting point, shown in the dashboard so it is never hidden.
STAGE_ODDS = {"new": 0.10, "contacted": 0.25, "booked": 0.60, "won": 1.0, "lost": 0.0}


def effective_value(lead: dict, average_cents: int) -> int:
    """A lead's own value if set, otherwise the client's average lead value."""
    return int(lead.get("value_cents") or 0) or int(average_cents or 0)


def forecast(rows: list[dict], average_cents: int, per_stage: int = 50) -> dict:
    """Group leads into stages and total them. Pure, so the arithmetic is easy to test."""
    stages = {s: {"count": 0, "value_cents": 0, "leads": []} for s in STAGES}
    for lead in rows:
        status = lead.get("status") if lead.get("status") in stages else "new"
        value = effective_value(lead, average_cents)
        bucket = stages[status]
        bucket["count"] += 1
        bucket["value_cents"] += value
        if len(bucket["leads"]) < per_stage:
            bucket["leads"].append({**lead, "effective_value_cents": value})
    open_value = sum(stages[s]["value_cents"] for s in OPEN_STAGES)
    weighted = round(sum(stages[s]["value_cents"] * STAGE_ODDS[s] for s in OPEN_STAGES))
    return {
        "stages": stages,
        "open_value_cents": open_value,
        "weighted_value_cents": weighted,
        "won_value_cents": stages["won"]["value_cents"],
        "odds": STAGE_ODDS,
    }


async def change_status(lead_id, status: str, reason: str = "") -> dict | None:
    """Move a lead to a stage, record it, and tidy its follow-up. Returns the updated lead, or None if unknown."""
    if status not in STAGES:
        raise ValueError("unknown stage")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            old = await conn.fetchrow("SELECT * FROM leads WHERE id = $1::uuid FOR UPDATE", lead_id)
            if old is None:
                return None
            if old["status"] == status:
                return dict(old)
            row = await conn.fetchrow(
                """
                UPDATE leads SET status = $2, updated_at = now(),
                    won_at = CASE WHEN $2 = 'won' THEN now() ELSE won_at END,
                    lost_at = CASE WHEN $2 = 'lost' THEN now() ELSE lost_at END,
                    lost_reason = CASE WHEN $2 = 'lost' THEN $3 ELSE lost_reason END
                WHERE id = $1::uuid RETURNING *
                """,
                lead_id, status, (reason or "")[:300],
            )
            await conn.execute(
                "INSERT INTO lead_events (lead_id, tenant_id, from_status, to_status, note) VALUES ($1, $2, $3, $4, $5)",
                old["id"], old["tenant_id"], old["status"], status, (reason or "")[:300],
            )
            if status != "new":
                await conn.execute(
                    "UPDATE tasks SET status = 'done', completed_at = now() "
                    "WHERE lead_id = $1 AND kind = 'follow_up' AND status = 'open'", old["id"])
    return dict(row)


async def pipeline(tenant: dict, per_stage: int = 50) -> dict:
    """The board: every open lead, plus anything won or lost in the last 30 days."""
    rows = await db.pool().fetch(
        """
        SELECT id, name, phone, email, message, channel, status, score, score_label, value_cents,
               next_action_at, lost_reason, won_at, lost_at, created_at
        FROM leads
        WHERE tenant_id = $1 AND (status NOT IN ('won', 'lost') OR updated_at > now() - interval '30 days')
        ORDER BY score DESC, created_at DESC LIMIT 1000
        """,
        tenant["id"],
    )
    result = forecast([dict(r) for r in rows], int(tenant.get("lead_value_cents") or 0), per_stage)
    result["average_lead_value_cents"] = int(tenant.get("lead_value_cents") or 0)
    return result


async def summary(tenant: dict, days: int = 7) -> dict:
    """What happened in the last `days` days, plus where things stand now."""
    p = db.pool()
    tid, avg = tenant["id"], int(tenant.get("lead_value_cents") or 0)
    window = f"now() - make_interval(days => {int(days)})"
    new_leads = await p.fetchval(f"SELECT count(*) FROM leads WHERE tenant_id = $1 AND created_at > {window}", tid)
    moved = {r["to_status"]: r["n"] for r in await p.fetch(
        f"SELECT to_status, count(*) AS n FROM lead_events WHERE tenant_id = $1 AND created_at > {window} "
        "GROUP BY to_status", tid)}
    won_rows = await p.fetch(
        f"SELECT value_cents FROM leads WHERE tenant_id = $1 AND status = 'won' AND won_at > {window}", tid)
    won_value = sum(effective_value(dict(r), avg) for r in won_rows)
    board = await pipeline(tenant, per_stage=0)
    won, lost = len(won_rows), int(moved.get("lost", 0))
    waiting = len(await sla.overdue(tenant)) if tenant.get("sla_minutes") else None
    return {
        "days": days,
        "new_leads": new_leads,
        "contacted": int(moved.get("contacted", 0)),
        "booked": int(moved.get("booked", 0)),
        "won": won,
        "won_value_cents": won_value,
        "lost": lost,
        "win_rate": round(won / (won + lost), 2) if (won + lost) else None,
        "open_value_cents": board["open_value_cents"],
        "weighted_value_cents": board["weighted_value_cents"],
        "overdue_todos": await tasks.overdue_count(tid),
        "leads_waiting": waiting,
    }


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def digest_text(tenant: dict, s: dict) -> tuple[str, str]:
    subject = f"Your week at {tenant['name']}: {s['new_leads']} new lead(s), {s['won']} won"
    lines = [
        f"Here is the last {s['days']} days for {tenant['name']}.",
        "",
        f"New leads: {s['new_leads']}",
        f"Moved to contacted: {s['contacted']}   Booked: {s['booked']}",
        f"Won: {s['won']} ({_money(s['won_value_cents'])})   Lost: {s['lost']}",
        f"Open pipeline: {_money(s['open_value_cents'])}   Weighted: {_money(s['weighted_value_cents'])}",
        f"To-dos overdue: {s['overdue_todos']}",
    ]
    if s["leads_waiting"] is not None:
        lines.append(f"Leads waiting for a reply: {s['leads_waiting']}")
    lines += ["", "Open the dashboard for the pipeline and to-do list."]
    return subject, "\n".join(lines) + "\n"


def digest_is_due(local: datetime) -> bool:
    """Monday, between 8am and 9pm local time, so a digest never arrives overnight."""
    return local.weekday() == 0 and 8 <= local.hour < 21


async def check_digests(now: datetime | None = None) -> int:
    """Queue this week's summary email for every client that switched it on. One per client per week."""
    now = now or datetime.now(timezone.utc)
    queued = 0
    for row in await db.pool().fetch(
            "SELECT * FROM tenants WHERE weekly_digest = true AND notify_email IS NOT NULL AND notify_email <> ''"):
        tenant = dict(row)
        if not is_email(tenant["notify_email"]):
            continue
        local = now.astimezone(ZoneInfo(tenant["timezone"]))
        if not digest_is_due(local):
            continue
        year, week, _ = local.isocalendar()
        key = f"digest:{tenant['id']}:{year}-W{week:02d}"
        if await db.pool().fetchval("SELECT 1 FROM outbox WHERE dedupe_key = $1", key):
            continue
        subject, body = digest_text(tenant, await summary(tenant, 7))
        if await outbox.enqueue(tenant["id"], "owner_alert", "email", tenant["notify_email"], body,
                                subject=subject, dedupe_key=key):
            queued += 1
    return queued


async def run_forever(stop: asyncio.Event) -> None:
    """Check for due weekly summaries every few minutes. Cheap: it exits early when nothing is due."""
    interval = max(get_settings().digest_poll_seconds, 30)
    while not stop.is_set():
        try:
            await check_digests()
        except Exception:
            log.exception("digest loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
