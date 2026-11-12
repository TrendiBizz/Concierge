"""After-call intelligence: a summary, an outcome, sentiment and a next step for every call.

Competitor-gap item D. Octovox sells "outcome classification" per call and GoHighLevel sells
Conversation AI summaries, both because an owner will not read a transcript. Concierge already
stores every call transcript (`conversations`/`messages`) and already has the model wired
(`llm.py`), so the missing piece is the judgement, the record and the follow-up.

Rules that keep this cheap and honest:
  * Deterministic first: a call with no caller turns gets no analysis at all, and a call that
    produced an appointment is recorded as `booked` without asking the model to guess.
  * One model call per conversation, never re-derived; the result is persisted in `call_insights`
    with the model name.
  * The model's answer is parsed defensively (`parse_analysis`): unknown outcomes are downgraded to
    `unresolved`, an unusable reply is discarded rather than half-written.
  * An unresolved or callback outcome creates the owner a task, because the whole point is that
    nothing waits for someone to watch a transcript.
  * Per-tenant daily cap, so a runaway loop cannot spend the operator's xAI budget.
"""

import json
import logging
import re
from datetime import datetime, timezone

from . import db, llm

log = logging.getLogger("concierge.call_insights")

OUTCOMES = (
    "booked",              # an appointment was made
    "quote_requested",     # they want a price
    "call_back",           # they want a human to ring them
    "information_only",    # question answered, no follow-up needed
    "not_interested",      # explicitly no
    "wrong_number",        # not a customer
    "unresolved",          # the AI could not help
)
SENTIMENTS = ("positive", "neutral", "negative")
NEEDS_FOLLOW_UP = ("call_back", "unresolved")

DAILY_CAP = 50          # per tenant, per day; a cap on spend, not on features
SWEEP_HOURS = 6

SYSTEM = (
    "You analyse one finished phone call between an AI receptionist and a caller. "
    "Reply with JSON only, no prose and no code fences, exactly these keys: "
    '{"summary": string (max 40 words, plain English, what the caller wanted and what happened), '
    '"outcome": one of ' + ", ".join(OUTCOMES) + ", "
    '"sentiment": one of ' + ", ".join(SENTIMENTS) + ' (how the caller felt), '
    '"next_step": string (max 20 words, the one action the business should take; '
    '"none" if nothing is needed)}. '
    "Never invent facts that are not in the transcript."
)


def parse_analysis(raw: str) -> dict | None:
    """Turn a model reply into a validated record, or None if it is unusable.

    Models wrap JSON in prose or fences, so the first {...} block is extracted. Anything that does
    not validate is rejected: a half-understood call is worse than an honest "no analysis".
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    summary = " ".join(str(data.get("summary") or "").split())[:400]
    outcome = str(data.get("outcome") or "").strip().lower()
    sentiment = str(data.get("sentiment") or "").strip().lower()
    next_step = " ".join(str(data.get("next_step") or "").split())[:200]
    if not summary:
        return None
    if outcome not in OUTCOMES:
        outcome = "unresolved"
    if sentiment not in SENTIMENTS:
        sentiment = "neutral"
    if next_step.lower() in ("none", "n/a", "-", ""):
        next_step = ""
    return {"summary": summary, "outcome": outcome, "sentiment": sentiment,
            "next_step": next_step}


def deterministic_outcome(*, appointment_created: bool, caller_turns: int) -> str | None:
    """Answers that need no model. None means "ask the model"."""
    if caller_turns <= 0:
        return "no_conversation"
    if appointment_created:
        return "booked"
    return None


def needs_follow_up(outcome: str) -> bool:
    return outcome in NEEDS_FOLLOW_UP


async def _transcript(tenant_id, session_id: str) -> list[dict]:
    rows = await db.pool().fetch(
        """
        SELECT m.role, m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.tenant_id = $1 AND c.session_id = $2 AND m.role IN ('user', 'assistant')
        ORDER BY m.id
        """,
        tenant_id, session_id,
    )
    return [dict(row) for row in rows]


async def _lead_for(tenant_id, session_id: str):
    return await db.pool().fetchrow(
        """
        SELECT l.id, l.case_id, l.name, l.phone FROM leads l
        JOIN conversations c ON c.id = l.conversation_id
        WHERE l.tenant_id = $1 AND c.session_id = $2
        ORDER BY l.created_at DESC LIMIT 1
        """,
        tenant_id, session_id,
    )


async def _appointment_exists(tenant_id, call) -> bool:
    return bool(await db.pool().fetchval(
        """SELECT 1 FROM appointments
           WHERE tenant_id = $1 AND created_at >= $2
             AND ($3 = '' OR phone = $3)
           LIMIT 1""",
        tenant_id, call.get("started_at"), call.get("from_number") or "",
    ))


async def _already_done(tenant_id, session_id: str) -> bool:
    return bool(await db.pool().fetchval(
        "SELECT 1 FROM call_insights WHERE tenant_id = $1 AND call_sid = $2", tenant_id, session_id))


async def _over_cap(tenant_id) -> bool:
    used = await db.pool().fetchval(
        "SELECT count(*) FROM call_insights WHERE tenant_id = $1 "
        "AND created_at > now() - interval '1 day'", tenant_id)
    return int(used or 0) >= DAILY_CAP


async def _persist(tenant_id, call_sid, lead_id, analysis: dict, model: str) -> None:
    await db.pool().execute(
        """INSERT INTO call_insights(call_sid, tenant_id, lead_id, summary, outcome, sentiment,
                                    next_step, model)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8)
           ON CONFLICT (tenant_id, call_sid) DO NOTHING""",
        call_sid, tenant_id, lead_id, analysis["summary"], analysis["outcome"],
        analysis["sentiment"], analysis["next_step"], model[:80],
    )


async def _follow_up_task(tenant_id, lead, analysis: dict) -> None:
    """One open task per lead for a callback/unresolved call; never a duplicate."""
    if not lead:
        return
    title = (f"Ring back: {lead.get('name') or lead.get('phone') or 'caller'}"
             if analysis["outcome"] == "call_back" else
             f"Unresolved call: {lead.get('name') or lead.get('phone') or 'caller'}")
    existing = await db.pool().fetchval(
        "SELECT 1 FROM tasks WHERE tenant_id = $1 AND lead_id = $2 AND status = 'open' "
        "AND title = $3 LIMIT 1", tenant_id, lead["id"], title[:200])
    if existing:
        return
    await db.pool().execute(
        """INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, case_id)
           VALUES ($1, $2, $3, $4, now() + interval '1 day', 'call_back', 'system', $5)""",
        tenant_id, lead["id"], title[:200],
        (analysis["summary"] + "\n" + analysis["next_step"])[:1000],
        lead.get("case_id"),
    )


async def analyse_call(tenant: dict, call: dict) -> dict | None:
    """Analyse one finished call. Idempotent on (tenant, call_sid)."""
    session_id = call.get("session_id") or call.get("call_sid")
    if not session_id or await _already_done(tenant["id"], session_id):
        return None
    turns = await _transcript(tenant["id"], session_id)
    caller_turns = sum(1 for turn in turns if turn["role"] == "user")
    appointment = await _appointment_exists(tenant["id"], call)
    quick = deterministic_outcome(appointment_created=appointment, caller_turns=caller_turns)
    if quick == "no_conversation":
        return None
    lead = await _lead_for(tenant["id"], session_id)
    if await _over_cap(tenant["id"]):
        log.info("call insights daily cap reached for %s", tenant.get("slug"))
        return None
    transcript = "\n".join(
        ("Customer: " if turn["role"] == "user" else "Receptionist: ")
        + (turn["content"] or "")[:1500]
        for turn in turns[-40:]
    )[:12000]
    analysis = None
    model = "deterministic"
    try:
        message = await llm.complete(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": "Transcript:\n" + transcript}],
            temperature=0.2, max_tokens=400,
        )
        analysis = parse_analysis(getattr(message, "content", "") or "")
        from .config import get_settings
        model = get_settings().chat_model
    except Exception as error:  # no key, provider down, bad reply: record what we do know
        log.warning("call analysis model failed for %s: %s", session_id, type(error).__name__)
    if analysis is None:
        analysis = {
            "summary": "Call ended; no automatic summary was available.",
            "outcome": quick or "unresolved",
            "sentiment": "neutral",
            "next_step": "Listen to the recording or read the transcript.",
        }
    if quick == "booked":
        analysis["outcome"] = "booked"
    await _persist(tenant["id"], session_id, lead["id"] if lead else None, analysis, model)
    if needs_follow_up(analysis["outcome"]):
        try:
            await _follow_up_task(tenant["id"], lead, analysis)
        except Exception:
            log.exception("call follow-up task failed for %s", session_id)
    return analysis


async def analyse_call_sid(call_sid: str) -> dict | None:
    if not call_sid:
        return None
    row = await db.pool().fetchrow(
        """SELECT p.*, t.* FROM phone_calls p JOIN tenants t ON t.id = p.tenant_id
           WHERE p.call_sid = $1""", call_sid)
    if not row:
        return None
    data = dict(row)
    from .missed_calls import CALL_COLUMNS

    tenant = {k: v for k, v in data.items() if k not in CALL_COLUMNS}
    tenant["id"] = data["tenant_id"]
    call = {k: data.get(k) for k in CALL_COLUMNS}
    return await analyse_call(tenant, call)


async def sweep(limit: int = 50) -> int:
    """Analyse ended calls that never got one — covers a deploy during the call."""
    rows = await db.pool().fetch(
        """SELECT p.call_sid FROM phone_calls p
           LEFT JOIN call_insights i
             ON i.tenant_id = p.tenant_id AND i.call_sid = COALESCE(p.session_id, p.call_sid)
           WHERE p.ended_at IS NOT NULL
             AND p.ended_at > now() - interval '1 hour' * $2
             AND i.id IS NULL
           ORDER BY p.ended_at DESC LIMIT $1""",
        limit, SWEEP_HOURS)
    handled = 0
    for row in rows:
        try:
            if await analyse_call_sid(row["call_sid"]):
                handled += 1
        except Exception:
            log.exception("call analysis failed for %s", row["call_sid"])
    return handled


async def run_forever(stop, interval: int = 300) -> None:
    import asyncio

    while not stop.is_set():
        try:
            await sweep()
        except Exception:
            log.exception("call insights sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def recent(tenant_id, limit: int = 20) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT i.call_sid, i.summary, i.outcome, i.sentiment, i.next_step, i.created_at,
                  p.from_number, p.started_at
           FROM call_insights i
           LEFT JOIN phone_calls p ON p.call_sid = i.call_sid AND p.tenant_id = i.tenant_id
           WHERE i.tenant_id = $1 ORDER BY i.created_at DESC LIMIT $2""",
        tenant_id, max(1, min(limit, 100)))
    insights = []
    for row in rows:
        item = dict(row)
        for key in ("created_at", "started_at"):
            if item.get(key):
                item[key] = item[key].isoformat()
        insights.append(item)
    return insights
