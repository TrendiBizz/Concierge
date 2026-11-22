"""N12 Analytics Upgrade:
- AI resolution / containment rate
- First-response-time SLAs (median p50, p95, % within tenant SLA)
- CSAT capture (public widget endpoint + owner summary)
- Date-range reporting (7d / 30d / 90d / custom from_date..to_date) with daily trend series
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import db, owner_auth, tenants

owner_router = APIRouter(prefix="/owner/analytics", tags=["analytics"])
public_router = APIRouter(prefix="/api/v1", tags=["analytics"])


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac, 2)


class CsatSubmit(BaseModel):
    key: str = Field(min_length=4, max_length=128)
    session_id: str = Field(default="", max_length=128)
    channel: str = Field(default="chat", pattern=r"^(chat|sms|voice|email)$")
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


@public_router.post("/csat", status_code=201)
async def submit_csat(body: CsatSubmit):
    tenant_id = await db.pool().fetchval("SELECT id FROM tenants WHERE public_key=$1", body.key)
    if not tenant_id:
        raise HTTPException(404, "Unknown business key")
    conv_id = None
    if body.session_id.strip():
        conv_id = await db.pool().fetchval(
            "SELECT id FROM conversations WHERE tenant_id=$1 AND session_id=$2",
            tenant_id, body.session_id.strip(),
        )
    row = await db.pool().fetchrow(
        "INSERT INTO csat_responses(tenant_id, conversation_id, channel, rating, comment) "
        "VALUES($1, $2, $3, $4, $5) RETURNING id, created_at",
        tenant_id, conv_id, body.channel, body.rating, body.comment.strip(),
    )
    return {"id": str(row["id"]), "rating": body.rating, "created_at": row["created_at"].isoformat()}


def _resolve_range(days: int, from_date: str, to_date: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if from_date and to_date:
        try:
            d0 = date.fromisoformat(from_date)
            d1 = date.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(400, "Use YYYY-MM-DD dates") from None
        if d1 < d0 or (d1 - d0).days > 366:
            raise HTTPException(400, "Date range must be 1 to 366 days")
        start = datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc)
        end = datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc) + timedelta(days=1)
        return start, end
    end = now
    start = now - timedelta(days=days)
    return start, end


@owner_router.get("/summary")
async def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    from_date: str = Query(default=""),
    to_date: str = Query(default=""),
    user: dict = Depends(owner_auth.current_user),
):
    start, end = _resolve_range(days, from_date, to_date)
    tid = user["tenant_id"]

    # 1. AI resolution / containment rate
    conv_rows = await db.pool().fetch(
        """
        SELECT c.id, c.started_at,
               EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.role = 'owner') AS has_human_reply,
               EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.role = 'assistant') AS has_ai_reply
        FROM conversations c
        WHERE c.tenant_id = $1 AND c.started_at >= $2 AND c.started_at < $3
        """,
        tid, start, end,
    )
    total_conv = len(conv_rows)
    human_escalated = sum(1 for r in conv_rows if r["has_human_reply"])
    ai_resolved = sum(1 for r in conv_rows if r["has_ai_reply"] and not r["has_human_reply"])
    resolution_rate = round((ai_resolved / total_conv) * 100.0, 1) if total_conv else 0.0

    # 2. First-response-time SLA (seconds between first user turn and first assistant/owner reply)
    sla_minutes = await db.pool().fetchval("SELECT sla_minutes FROM tenants WHERE id=$1", tid) or 15
    sla_target_sec = max(int(sla_minutes), 1) * 60.0
    lat_rows = await db.pool().fetch(
        """
        WITH first_user AS (
            SELECT m.conversation_id, min(m.created_at) AS u_at
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE c.tenant_id = $1 AND c.started_at >= $2 AND c.started_at < $3 AND m.role = 'user'
            GROUP BY m.conversation_id
        ),
        first_reply AS (
            SELECT m.conversation_id, min(m.created_at) AS r_at
            FROM messages m JOIN first_user fu ON fu.conversation_id = m.conversation_id
            WHERE m.role IN ('assistant', 'owner') AND m.created_at >= fu.u_at
            GROUP BY m.conversation_id
        )
        SELECT extract(epoch FROM (fr.r_at - fu.u_at)) AS latency_sec
        FROM first_user fu JOIN first_reply fr ON fr.conversation_id = fu.conversation_id
        ORDER BY latency_sec ASC
        """,
        tid, start, end,
    )
    latencies = [max(0.0, float(r["latency_sec"])) for r in lat_rows]
    within_sla = sum(1 for x in latencies if x <= sla_target_sec)
    sla_compliance = round((within_sla / len(latencies)) * 100.0, 1) if latencies else 100.0

    # 3. CSAT summary
    csat_rows = await db.pool().fetch(
        "SELECT rating FROM csat_responses WHERE tenant_id=$1 AND created_at >= $2 AND created_at < $3",
        tid, start, end,
    )
    ratings = [int(r["rating"]) for r in csat_rows]
    breakdown = {str(star): ratings.count(star) for star in range(1, 6)}
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    satisfied_pct = round((sum(1 for x in ratings if x >= 4) / len(ratings)) * 100.0, 1) if ratings else None

    # 4. Daily trend series
    lead_rows = await db.pool().fetch(
        "SELECT date_trunc('day', created_at)::date AS d, count(*) AS cnt "
        "FROM leads WHERE tenant_id=$1 AND created_at >= $2 AND created_at < $3 GROUP BY 1",
        tid, start, end,
    )
    leads_by_day = {r["d"].isoformat(): int(r["cnt"]) for r in lead_rows}
    daily_map: dict[str, dict] = {}
    for r in conv_rows:
        dkey = r["started_at"].astimezone(timezone.utc).date().isoformat()
        bucket = daily_map.setdefault(dkey, {"date": dkey, "conversations": 0, "ai_resolved": 0, "leads": leads_by_day.get(dkey, 0)})
        bucket["conversations"] += 1
        if r["has_ai_reply"] and not r["has_human_reply"]:
            bucket["ai_resolved"] += 1
    for dkey, cnt in leads_by_day.items():
        daily_map.setdefault(dkey, {"date": dkey, "conversations": 0, "ai_resolved": 0, "leads": cnt})
    daily = [daily_map[k] for k in sorted(daily_map)]

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days},
        "ai_resolution": {
            "total_conversations": total_conv,
            "ai_resolved": ai_resolved,
            "human_escalated": human_escalated,
            "resolution_rate_pct": resolution_rate,
        },
        "response_sla": {
            "sample_count": len(latencies),
            "p50_seconds": _percentile(latencies, 50),
            "p95_seconds": _percentile(latencies, 95),
            "target_minutes": int(sla_minutes),
            "within_sla_pct": sla_compliance,
        },
        "csat": {
            "responses": len(ratings),
            "average_rating": avg_rating,
            "satisfied_pct": satisfied_pct,
            "breakdown": breakdown,
        },
        "daily": daily,
    }
