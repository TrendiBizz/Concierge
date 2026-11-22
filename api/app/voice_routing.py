"""N14 Voice Operational Essentials:
- Schedule-aware business-hours call routing (ring owner during hours, AI overflow/after-hours)
- Caller blocklist & spam screening (exact E.164 or prefix wildcard, e.g. +64900*)
- Warm transfer with caller summary brief on the existing Asterisk/PBX path

Hero landline remains voicemail-only; all call control uses the existing Asterisk AMI path.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import call_control, contact, db, owner_auth

router = APIRouter(prefix="/owner/voice", tags=["voice-routing"])

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HHMM = re.compile(r"^\d{2}:\d{2}$")
PATTERN_RE = re.compile(r"^(\+?[0-9]{3,16}\*?|anonymous|private|unknown)$", re.I)

DEFAULT_BUSINESS_HOURS: dict[str, list[str]] = {
    "mon": ["08:30", "17:00"],
    "tue": ["08:30", "17:00"],
    "wed": ["08:30", "17:00"],
    "thu": ["08:30", "17:00"],
    "fri": ["08:30", "17:00"],
    "sat": [],
    "sun": [],
}


def is_within_business_hours(
    schedule: dict | None,
    tz_name: str = "Pacific/Auckland",
    now: datetime | None = None,
) -> bool:
    """Return True if `now` falls inside one of the configured local-time windows."""
    if not schedule or not isinstance(schedule, dict):
        return False
    try:
        tz = ZoneInfo(tz_name or "Pacific/Auckland")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Pacific/Auckland")
    dt = (now or datetime.now(timezone.utc)).astimezone(tz)
    day_key = DAY_KEYS[dt.weekday()]
    window = schedule.get(day_key)
    if not window or not isinstance(window, list) or len(window) != 2:
        return False
    start_s, end_s = str(window[0]), str(window[1])
    if not (HHMM.match(start_s) and HHMM.match(end_s)):
        return False
    cur = dt.strftime("%H:%M")
    return start_s <= cur < end_s


def matches_block_pattern(caller: str, pattern: str) -> bool:
    """Match normalized caller number against an exact pattern or trailing `*` prefix."""
    c = (caller or "").strip().lower()
    p = (pattern or "").strip().lower()
    if not c or not p:
        return False
    if p in ("anonymous", "private", "unknown"):
        return c in ("anonymous", "private", "unknown", "")
    if p.endswith("*"):
        prefix = p[:-1]
        return c.startswith(prefix) or c.lstrip("+").startswith(prefix.lstrip("+"))
    if c == p:
        return True
    return c.lstrip("+") == p.lstrip("+")


async def is_caller_blocked(tenant_id, caller_number: str) -> tuple[bool, str]:
    rows = await db.pool().fetch(
        "SELECT phone_pattern, reason FROM voice_caller_blocklist WHERE tenant_id=$1",
        tenant_id,
    )
    norm = contact.normalize_phone(caller_number, default_cc="64") if caller_number and caller_number[0] in "+0123456789" else caller_number
    for r in rows:
        if matches_block_pattern(caller_number, r["phone_pattern"]) or (
            norm and matches_block_pattern(norm, r["phone_pattern"])
        ):
            return True, r["reason"] or "Blocked caller"
    return False, ""


async def evaluate_inbound_call(
    tenant_id,
    caller_number: str,
    *,
    now: datetime | None = None,
) -> dict:
    """Decide how to route an inbound call: block, ring_owner_then_ai, ai_only, or voicemail."""
    blocked, reason = await is_caller_blocked(tenant_id, caller_number)
    if blocked:
        return {"action": "block", "blocked": True, "reason": reason, "within_hours": False}
    cfg = await db.pool().fetchrow(
        "SELECT business_hours, timezone, during_hours_action, after_hours_action, "
        "ring_owner_number, ring_seconds, spam_max_calls_10m "
        "FROM tenant_voice_routing WHERE tenant_id=$1",
        tenant_id,
    )
    if not cfg:
        return {"action": "ai_only", "blocked": False, "reason": "default", "within_hours": True}

    # Optional automatic spam flood guard (e.g. > N calls from same number in 10 minutes)
    max_10m = int(cfg["spam_max_calls_10m"] or 0)
    if max_10m > 0 and caller_number:
        recent = await db.pool().fetchval(
            "SELECT count(*) FROM phone_calls WHERE tenant_id=$1 AND from_number=$2 "
            "AND started_at > now() - interval '10 minutes'",
            tenant_id, caller_number,
        )
        if int(recent or 0) >= max_10m:
            return {"action": "block", "blocked": True, "reason": "auto_spam_rate_limit", "within_hours": False}

    hours = json.loads(cfg["business_hours"]) if isinstance(cfg["business_hours"], str) else (cfg["business_hours"] or {})
    within = is_within_business_hours(hours, cfg["timezone"] or "Pacific/Auckland", now=now)
    action = cfg["during_hours_action"] if within else cfg["after_hours_action"]
    return {
        "action": action,
        "blocked": False,
        "reason": "business_hours" if within else "after_hours",
        "within_hours": within,
        "ring_owner_number": cfg["ring_owner_number"] or "",
        "ring_seconds": int(cfg["ring_seconds"] or 15),
    }


# ---- Owner routing config endpoints ---------------------------------------------------------
class VoiceRoutingUpdate(BaseModel):
    business_hours: dict[str, list[str]] = Field(default_factory=lambda: dict(DEFAULT_BUSINESS_HOURS))
    timezone: str = Field(default="Pacific/Auckland", max_length=80)
    during_hours_action: Literal["ring_owner_then_ai", "ai_only", "ring_owner_only"] = "ring_owner_then_ai"
    after_hours_action: Literal["ai_only", "voicemail"] = "ai_only"
    ring_owner_number: str = Field(default="", max_length=32)
    ring_seconds: int = Field(default=15, ge=5, le=45)
    spam_max_calls_10m: int = Field(default=0, ge=0, le=50)


@router.get("/routing")
async def get_voice_routing(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT business_hours, timezone, during_hours_action, after_hours_action, "
        "ring_owner_number, ring_seconds, spam_max_calls_10m, updated_at "
        "FROM tenant_voice_routing WHERE tenant_id=$1",
        user["tenant_id"],
    )
    if not row:
        return {
            "business_hours": DEFAULT_BUSINESS_HOURS,
            "timezone": "Pacific/Auckland",
            "during_hours_action": "ai_only",
            "after_hours_action": "ai_only",
            "ring_owner_number": "",
            "ring_seconds": 15,
            "spam_max_calls_10m": 0,
        }
    out = dict(row)
    if isinstance(out["business_hours"], str):
        out["business_hours"] = json.loads(out["business_hours"])
    return out


@router.put("/routing")
async def save_voice_routing(body: VoiceRoutingUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(400, "Unknown IANA timezone") from None
    clean_hours: dict[str, list[str]] = {}
    for day in DAY_KEYS:
        win = body.business_hours.get(day) or []
        if not win:
            clean_hours[day] = []
        elif len(win) == 2 and HHMM.match(win[0]) and HHMM.match(win[1]) and win[0] < win[1]:
            clean_hours[day] = [win[0], win[1]]
        else:
            raise HTTPException(400, f"Invalid business hours window for {day}")
    num = body.ring_owner_number.strip()
    if num and not re.fullmatch(r"\+[1-9]\d{6,14}", num):
        raise HTTPException(400, "ring_owner_number must be E.164 (e.g. +64211234567)")
    await db.pool().execute(
        """INSERT INTO tenant_voice_routing(
               tenant_id, business_hours, timezone, during_hours_action, after_hours_action,
               ring_owner_number, ring_seconds, spam_max_calls_10m, updated_at)
           VALUES($1, $2::jsonb, $3, $4, $5, $6, $7, $8, now())
           ON CONFLICT (tenant_id) DO UPDATE SET
               business_hours=$2::jsonb, timezone=$3, during_hours_action=$4,
               after_hours_action=$5, ring_owner_number=$6, ring_seconds=$7,
               spam_max_calls_10m=$8, updated_at=now()""",
        user["tenant_id"], json.dumps(clean_hours), body.timezone, body.during_hours_action,
        body.after_hours_action, num, body.ring_seconds, body.spam_max_calls_10m,
    )
    return {
        "business_hours": clean_hours,
        "timezone": body.timezone,
        "during_hours_action": body.during_hours_action,
        "after_hours_action": body.after_hours_action,
        "ring_owner_number": num,
        "ring_seconds": body.ring_seconds,
        "spam_max_calls_10m": body.spam_max_calls_10m,
    }


# ---- Caller blocklist CRUD ------------------------------------------------------------------
class BlocklistAdd(BaseModel):
    phone_pattern: str = Field(min_length=3, max_length=32)
    reason: str = Field(default="", max_length=200)


@router.get("/blocklist")
async def list_blocklist(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, phone_pattern, reason, source, created_at "
        "FROM voice_caller_blocklist WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 500",
        user["tenant_id"],
    )
    return [dict(r) for r in rows]


@router.post("/blocklist", status_code=201)
async def add_blocklist(body: BlocklistAdd, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    pat = body.phone_pattern.strip()
    if not PATTERN_RE.fullmatch(pat):
        raise HTTPException(400, "Enter an E.164 number, prefix with *, or anonymous/private")
    row = await db.pool().fetchrow(
        """INSERT INTO voice_caller_blocklist(tenant_id, phone_pattern, reason, source)
           VALUES($1, $2, $3, 'owner')
           ON CONFLICT (tenant_id, phone_pattern) DO UPDATE SET reason=$3
           RETURNING id, phone_pattern, reason, source, created_at""",
        user["tenant_id"], pat.lower() if pat.isalpha() else pat, body.reason.strip(),
    )
    return dict(row)


@router.delete("/blocklist/{entry_id}")
async def remove_blocklist(entry_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    res = await db.pool().execute(
        "DELETE FROM voice_caller_blocklist WHERE id=$1 AND tenant_id=$2",
        entry_id, user["tenant_id"],
    )
    if res.endswith("0"):
        raise HTTPException(404, "Blocklist entry not found")
    return {"ok": True}


# ---- Warm transfer endpoint -----------------------------------------------------------------
class WarmTransferBody(BaseModel):
    number: str = Field(min_length=3, max_length=32)
    brief: str = Field(default="", max_length=500)


@router.post("/calls/{call_sid}/warm-transfer")
async def warm_transfer(call_sid: str, body: WarmTransferBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    brief = body.brief.strip()
    if not brief:
        insight = await db.pool().fetchval(
            "SELECT summary FROM call_insights WHERE tenant_id=$1 AND call_sid=$2",
            user["tenant_id"], call_sid,
        )
        brief = (insight or "Incoming warm transfer from AI receptionist")[:500]
    try:
        channel = await call_control.warm_transfer_call(
            call_sid, user["slug"], body.number.strip(), brief=brief,
        )
    except call_control.CallControlUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    row = await db.pool().fetchrow(
        "INSERT INTO voice_warm_transfers(tenant_id, call_sid, target_number, brief, initiated_by) "
        "VALUES($1, $2, $3, $4, $5) RETURNING id, created_at",
        user["tenant_id"], call_sid, body.number.strip(), brief, user.get("email") or "owner",
    )
    return {
        "id": str(row["id"]),
        "call_sid": call_sid,
        "channel": channel,
        "target_number": body.number.strip(),
        "brief": brief,
        "created_at": row["created_at"].isoformat(),
    }
