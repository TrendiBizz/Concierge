"""Missed-call text-back: a caller who hangs up before the AI can help gets one reply and a lead.

Competitor note (2026-11-12 gap analysis, item A): GoHighLevel makes "Missed Call Text Back" a
headline feature on every plan because it is the fastest visible win an owner gets. Concierge
already answers calls with the AI; this covers the case the AI never got — a hang-up during the
greeting, an after-hours call while the receptionist is off, or a provider webhook that arrived
late.

What counts as missed, deliberately conservatively:
  * the call has ended, and
  * the caller never had a transcribed turn (they hung up before speaking) **or** the whole call
    lasted less than SHORT_CALL, and
  * no appointment was created for that caller around the time of the call.

Compliance basis: the caller dialled the business, so one service reply is a response to the
caller's own enquiry rather than marketing. It is still gated: the tenant can switch it off
(`tenants.missed_call_textback`), SMS must be enabled and authorised for the tenant, the outbox
enforces opt-outs and quiet hours, and there is at most one reply per number per day. Every
decision is written to `missed_call_recoveries`, so the owner can see what was sent and the audit
can explain why.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from . import casetimeline, channel_authorization, db, enquiries, outbox
from .contact import normalize_phone

log = logging.getLogger("concierge.missed_calls")

SHORT_CALL = timedelta(seconds=20)
DEDUPE_HOURS = 24
SWEEP_WINDOW = timedelta(hours=6)
STALE_RINGING = timedelta(minutes=2)

DEFAULT_TEMPLATE = (
    "Sorry we missed your call. Reply to this message and we will get straight back to you."
)

# Declared here rather than imported to keep this module's decision pure and testable.
CHANNEL = "phone"


def decide(
    *,
    tenant: dict,
    call: dict,
    caller_turns: int,
    has_appointment: bool,
    recovered_recently: bool,
    sms_authorized: bool,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return ("text" | "skip", reason). Pure: no I/O, so the rules are testable in isolation."""
    now = now or datetime.now(timezone.utc)
    if not tenant.get("missed_call_textback"):
        return "skip", "textback_disabled"
    if not tenant.get("sms_enabled"):
        return "skip", "sms_disabled"
    if not sms_authorized:
        return "skip", "sms_not_authorized"
    if not (call.get("from_number") or "").strip():
        return "skip", "no_caller_number"
    if call.get("to_number") and call.get("from_number") == call.get("to_number"):
        return "skip", "self_call"
    ended = call.get("ended_at")
    if not ended and call.get("status") not in ("missed", "no-answer", "busy", "failed", "canceled"):
        # Still ringing, or a live call: nothing to recover yet unless it has gone stale.
        if not (call.get("started_at") and now - call["started_at"] > STALE_RINGING):
            return "skip", "call_in_progress"
    if recovered_recently:
        return "skip", "recovered_recently"
    if has_appointment:
        return "skip", "already_booked"
    duration = (ended - call["started_at"]) if (ended and call.get("started_at")) else None
    if caller_turns > 0 and duration is not None and duration >= SHORT_CALL:
        return "skip", "call_was_answered"
    return "text", "hung_up_before_answering"


def compose_message(tenant: dict, booking_url: str) -> str:
    """The one SMS a missed caller receives. Tenant template first, then the default."""
    template = (tenant.get("missed_call_template") or "").strip() or DEFAULT_TEMPLATE
    if "{link}" in template:
        return template.replace("{link}", booking_url) if booking_url else template.replace(
            " {link}", "").replace("{link}", "")
    if booking_url and booking_url not in template:
        return f"{template} Book a time: {booking_url}"
    return template


async def _caller_turns(tenant_id, session_id: str | None) -> int:
    if not session_id:
        return 0
    value = await db.pool().fetchval(
        """SELECT count(*) FROM messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE c.tenant_id = $1 AND c.session_id = $2 AND m.role = 'user'""",
        tenant_id, session_id,
    )
    return int(value or 0)


async def _has_appointment(tenant_id, call: dict, contact: str) -> bool:
    started = call.get("started_at")
    value = await db.pool().fetchval(
        """SELECT 1 FROM appointments
           WHERE tenant_id = $1 AND phone = $2 AND created_at >= COALESCE($3, now() - interval '1 day')
           LIMIT 1""",
        tenant_id, contact, started,
    )
    return bool(value)


async def _recovered_recently(tenant_id, contact: str) -> bool:
    value = await db.pool().fetchval(
        """SELECT 1 FROM missed_call_recoveries
           WHERE tenant_id = $1 AND contact = $2 AND status = 'queued'
             AND created_at > now() - interval '1 hour' * $3
           LIMIT 1""",
        tenant_id, contact, DEDUPE_HOURS,
    )
    return bool(value)


async def _record(call: dict, contact: str, status: str, reason: str, outbox_id=None) -> None:
    await db.pool().execute(
        """INSERT INTO missed_call_recoveries(call_sid, tenant_id, contact, status, reason, outbox_id)
           VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT (tenant_id, call_sid) DO NOTHING""",
        call["call_sid"], call["tenant_id"], contact, status, reason[:80], outbox_id,
    )


async def evaluate_call(tenant: dict, call: dict) -> dict:
    """Decide and act for one ended call. Idempotent: the DB rows make a replay a no-op."""
    contact = normalize_phone(
        call.get("from_number") or "", casetimeline.tenant_country_code(tenant)
    ) or ""
    turns = await _caller_turns(tenant["id"], call.get("session_id"))
    authorized = await channel_authorization.is_authorized(tenant["id"], "sms")
    recovered = bool(contact) and await _recovered_recently(tenant["id"], contact)
    booked = bool(contact) and await _has_appointment(tenant["id"], call, contact)
    action, reason = decide(
        tenant=tenant, call=call, caller_turns=turns, has_appointment=booked,
        recovered_recently=recovered, sms_authorized=authorized,
    )
    if action != "text":
        await _record(call, contact, "skipped", reason)
        return {"action": "skip", "reason": reason}
    booking_url = (tenant.get("booking_url") or "").strip()
    body = compose_message(tenant, booking_url)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    dedupe_key = f"missed:{tenant['id']}:{contact}:{day}"
    queued = await outbox.enqueue(
        tenant["id"], "missed_call", "sms", contact, body, dedupe_key=dedupe_key,
    )
    outbox_id = await db.pool().fetchval(
        "SELECT id FROM outbox WHERE dedupe_key=$1", dedupe_key) if queued else None
    # The caller is a real enquiry even though the call produced no lead: record it on the
    # timeline and in the CRM, and let the owner's alert say what we did about it.
    try:
        lead = await enquiries.capture(
            tenant, CHANNEL, "missed:" + str(call["call_sid"]),
            "Missed call — no conversation happened. A text-back was attempted.",
            phone=contact,
        )
        lead_id = lead.get("id")
    except Exception:  # a recovery must never fail because the CRM write did
        log.exception("missed-call lead capture failed for %s", call["call_sid"])
        lead_id = None
    await _record(call, contact, "queued" if queued else "duplicate", reason, outbox_id)
    if lead_id:
        await db.pool().execute(
            "UPDATE missed_call_recoveries SET lead_id=$3 WHERE tenant_id=$1 AND call_sid=$2",
            tenant["id"], call["call_sid"], lead_id,
        )
    log.info("missed-call text-back queued for %s (%s)", contact, reason)
    return {"action": "text", "reason": reason, "contact": contact, "queued": queued}


async def evaluate_call_sid(call_sid: str) -> dict | None:
    """Load one call and its tenant, then evaluate. Used by both providers' end hooks."""
    if not call_sid:
        return None
    row = await db.pool().fetchrow(
        """SELECT p.*, t.* FROM phone_calls p JOIN tenants t ON t.id = p.tenant_id
           WHERE p.call_sid = $1""", call_sid)
    if not row:
        return None
    data = dict(row)
    tenant = {k: v for k, v in data.items() if k not in CALL_COLUMNS}
    tenant["id"] = data["tenant_id"]
    call = {k: data.get(k) for k in CALL_COLUMNS}
    return await evaluate_call(tenant, call)


# Columns `phone_calls` contributes when a join returns both rows.
CALL_COLUMNS = {"call_sid", "tenant_id", "session_id", "from_number", "to_number", "status",
                "started_at", "ended_at", "recording_consent", "recording_sid",
                "recording_status", "consent_at"}


async def sweep(limit: int = 100) -> int:
    """Find ended calls with no recovery decision yet and evaluate them.

    Covers both providers: the Grok SIP path writes `phone_calls` itself, and a Twilio call that
    ends without a session would otherwise be invisible forever.
    """
    rows = await db.pool().fetch(
        """SELECT p.* FROM phone_calls p
           JOIN tenants t ON t.id = p.tenant_id
           WHERE t.missed_call_textback
             AND p.ended_at IS NOT NULL
             AND p.ended_at > now() - interval '1 hour' * $2
             AND NOT EXISTS (SELECT 1 FROM missed_call_recoveries r
                             WHERE r.tenant_id = p.tenant_id AND r.call_sid = p.call_sid)
           ORDER BY p.ended_at DESC
           LIMIT $1""",
        limit, int(SWEEP_WINDOW.total_seconds() // 3600),
    )
    handled = 0
    for row in rows:
        call = dict(row)
        tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", call["tenant_id"])
        if not tenant:
            continue
        try:
            await evaluate_call(dict(tenant), call)
            handled += 1
        except Exception:
            log.exception("missed-call recovery failed for %s", call.get("call_sid"))
    return handled


async def run_forever(stop, interval: int = 300) -> None:
    """Sweep loop, matching outbox.reconcile_stale_device_sms' cadence."""
    while not stop.is_set():
        try:
            await sweep()
        except Exception:
            log.exception("missed-call sweep failed")
        try:
            await _sleep(stop, interval)
        except Exception:
            log.exception("missed-call sweep sleep failed")


async def _sleep(stop, seconds: int) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def recent(tenant_id, limit: int = 20) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT r.*, o.status AS outbox_status, o.body, o.sent_at
           FROM missed_call_recoveries r
           LEFT JOIN outbox o ON o.id = r.outbox_id
           WHERE r.tenant_id = $1
           ORDER BY r.created_at DESC LIMIT $2""",
        tenant_id, limit,
    )
    return [dict(row) for row in rows]
