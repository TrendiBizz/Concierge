"""Response-time alerts: tell the owner when an enquiry has been left waiting.

A client sets sla_minutes (0 = off) and sla_min_score. An enquiry is "waiting" when it is still status
'new', has no booked appointment, and is older than sla_minutes. The owner gets ONE email per lead
(dedupe key), sent inside the allowed hours (8am-9pm local), so a 3am lead produces a morning alert,
not a 3am one. Marking the lead contacted in the dashboard (or anything other than 'new') clears it.
Alerts are only raised for leads under two days old, so switching this on never floods the owner with
old leads.

TWO MODES, and the difference matters:

  sla_min_score > 0 (the default 70) -- "promising leads only". Enquiries scoring below the client's
      threshold are not chased. This is the original behaviour and stays the default.

  sla_min_score = 0 -- "every enquiry". The score filter is dropped entirely, so an inbound email or
      text is chased whatever it scored. This exists because a low score is not evidence that nobody
      needs an answer: scoring weighs phone/email/name/message, so a genuine one-line email from a new
      customer can score low and was previously never followed up at all. Choosing 0 is a deliberate
      opt-in, because it can increase the number of alerts the owner receives.

Either way the customer's own opt-out and an owner takeover always suppress the alert.
"""

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import db, outbox
from .config import get_settings
from .contact import is_email
from .outbox import next_allowed_send

log = logging.getLogger("concierge.sla")

ALERT_MAX_AGE_DAYS = 2      # never alert on older leads
LIST_MAX_AGE_DAYS = 7       # the dashboard list looks back further


async def overdue(tenant: dict, only_unalerted: bool = False, max_age_days: int = LIST_MAX_AGE_DAYS) -> list[dict]:
    """Enquiries that have waited longer than the client's target, across every channel.

    Honours the client's chosen mode: with sla_min_score > 0 only leads at or above the threshold are
    listed; with sla_min_score = 0 every enquiry is listed whatever it scored. Score always sets the
    ORDER, so a hot lead is surfaced first.

    Two exclusions are deliberate and must not be removed:
      - anyone on the opt-out list, because chasing them is a compliance failure;
      - any customer whose case the owner has taken over, because the owner is already handling it.

    Empty when the feature is off (sla_minutes = 0).
    """
    minutes = int(tenant.get("sla_minutes") or 0)
    if minutes <= 0:
        return []
    min_score = int(tenant.get("sla_min_score") if tenant.get("sla_min_score") is not None else 70)
    rows = await db.pool().fetch(
        f"""
        SELECT id, name, phone, email, message, channel, score, score_label, score_reasons,
               created_at, sla_alerted_at,
               floor(EXTRACT(EPOCH FROM (now() - created_at)) / 60)::int AS minutes_waiting
        FROM leads
        WHERE tenant_id = $1 AND status = 'new'
          {"AND score >= $4" if min_score > 0 else ""}
          AND created_at < now() - make_interval(mins => $2)
          AND created_at > now() - make_interval(days => $3)
          AND NOT EXISTS (SELECT 1 FROM appointments a
                          WHERE a.lead_id = leads.id AND a.status IN ('booked', 'completed'))
          AND NOT EXISTS (SELECT 1 FROM customer_cases c
                          WHERE c.id = leads.case_id AND c.automation_paused)
          AND NOT EXISTS (SELECT 1 FROM opt_outs o
                          WHERE o.tenant_id = leads.tenant_id
                            AND o.contact = ANY (ARRAY[
                                  CASE WHEN leads.email <> '' THEN lower(leads.email) END,
                                  CASE WHEN leads.phone <> '' THEN leads.phone END]))
          {"AND sla_alerted_at IS NULL" if only_unalerted else ""}
        ORDER BY score DESC, created_at
        LIMIT 100
        """,
        # Only pass the score argument when the clause using it was rendered, or asyncpg rejects
        # the statement for having more parameters than placeholders.
        *([tenant["id"], minutes, max_age_days, min_score] if min_score > 0
          else [tenant["id"], minutes, max_age_days]),
    )
    return [dict(r) for r in rows]


def _alert_text(tenant: dict, lead: dict) -> tuple[str, str]:
    who = lead["name"] or lead["phone"] or lead["email"] or "a visitor"
    subject = f"[ACTION] {lead['score_label'].upper()} lead waiting {lead['minutes_waiting']} min: {who}"
    body = (
        f"A {lead['score_label']} lead (score {lead['score']}/100) for {tenant['name']} has had no reply "
        f"for {lead['minutes_waiting']} minutes (your target is {tenant['sla_minutes']}).\n\n"
        f"Name: {lead['name']}\nPhone: {lead['phone']}\nEmail: {lead['email']}\nVia: {lead['channel']}\n\n"
        f"{lead['message']}\n\n"
        "Open the dashboard and mark the lead as contacted once you have replied, and this stops.\n"
    )
    return subject, body


async def check_once() -> int:
    """Raise the alerts that are due. Returns how many were queued."""
    tenant_rows = await db.pool().fetch(
        "SELECT * FROM tenants WHERE sla_minutes > 0 AND notify_email IS NOT NULL AND notify_email <> ''")
    queued = 0
    for row in tenant_rows:
        tenant = dict(row)
        if not is_email(tenant["notify_email"]):
            continue
        send_at = next_allowed_send(ZoneInfo(tenant["timezone"]), datetime.now(timezone.utc))
        for lead in await overdue(tenant, only_unalerted=True, max_age_days=ALERT_MAX_AGE_DAYS):
            subject, body = _alert_text(tenant, lead)
            await outbox.enqueue(
                tenant["id"], "owner_alert", "email", tenant["notify_email"], body, subject=subject,
                send_at=send_at, dedupe_key=f"lead:{lead['id']}:sla", lead_id=lead["id"],
            )
            await db.pool().execute("UPDATE leads SET sla_alerted_at = now() WHERE id = $1", lead["id"])
            queued += 1
    return queued


async def run_forever(stop: asyncio.Event) -> None:
    interval = max(get_settings().sla_poll_seconds, 10)
    while not stop.is_set():
        try:
            await check_once()
        except Exception:
            log.exception("sla loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
