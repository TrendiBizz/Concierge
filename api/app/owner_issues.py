"""ISSUE notices to the owner: something about an enquiry needs a person. Never a copy of the enquiry alert.

Three problem types, each raised AT MOST ONCE per enquiry (the outbox dedupe key is
``issue:<type>:<enquiry>``), each headed "ACTION NEEDED", each carrying no customer message text:

* ``alert_undelivered`` -- the enquiry alert itself ended failed / held / suppressed (e.g. owner SMS was
  never confirmed by the phone). Sent on a channel other than the one that failed, when one exists.
* ``unanswered``        -- a genuine enquiry has had no reply from the owner past the threshold.
* ``reply_failed``      -- the reply we tried to send to the customer could not be delivered.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import db, enquiry_alerts, outbox, owner_notifications, sla
from .config import get_settings

log = logging.getLogger("concierge.owner_issues")

WINDOW_HOURS = 24
FAILED_STATES = ("failed", "held", "suppressed")
CUSTOMER_REPLY_KINDS = ("email_secretary_reply", "inbound_ack", "approved_reply", "enquirer_ack")


async def raise_issue(tenant: dict, issue: str, anchor, subject: str, body: str, *, avoid=None,
                      lead_id=None, send_at=None, runner=None) -> bool:
    """Queue one notice. False when this enquiry already has one of this type, or there is nowhere to send it."""
    runner = runner or db.pool()
    route = await owner_notifications.delivery_route(runner, tenant, avoid=avoid)
    if route is None:
        log.error("ACTION NEEDED (%s, %s) could not be sent: no owner channel available", issue, anchor)
        return False
    channel, recipient = route
    subject = "ACTION NEEDED: " + subject
    if channel == "sms":
        body = owner_notifications.sms_body(subject, body)
    return await outbox.enqueue(
        tenant["id"], "owner_issue", channel, recipient, body, subject=subject,
        dedupe_key=f"issue:{issue}:{anchor}", lead_id=lead_id, send_at=send_at)


def _portal(settings=None) -> str:
    s = settings or get_settings()
    base = (getattr(s, "owner_portal_url", "") or "").strip()
    if base:
        return base.rstrip("/").rsplit("/owner-ui", 1)[0] + "/studio/"
    return s.public_base_url.rstrip("/") + "/studio/"


async def _tenant(tenant_id) -> dict | None:
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", tenant_id)
    return dict(row) if row else None


async def sweep_undelivered() -> int:
    rows = await db.pool().fetch(
        """SELECT o.id, o.tenant_id, o.channel, o.last_error, o.created_at, o.lead_id, o.dedupe_key,
                  l.name, l.email, l.phone, l.channel AS lead_channel
           FROM outbox o LEFT JOIN leads l ON l.id = o.lead_id
           WHERE o.kind='owner_alert' AND (o.dedupe_key LIKE 'enq:%' OR o.dedupe_key LIKE 'site-enquiry:%') AND o.status = ANY($1::text[])
             AND o.created_at > now() - make_interval(hours => $2)
           ORDER BY o.id DESC LIMIT 20""", list(FAILED_STATES), WINDOW_HOURS)
    raised = 0
    for row in rows:
        tenant = await _tenant(row["tenant_id"])
        if tenant is None:
            continue
        who = row["name"] or row["phone"] or row["email"] or "a customer"
        via = enquiry_alerts.label(row["lead_channel"] or "").lower()
        body = (f"We could not deliver the alert for a {via} from {who} "
                f"({row['created_at'].astimezone(timezone.utc):%d %b %H:%M} UTC) by {row['channel']}.\n"
                f"Reason: {row['last_error'] or row['channel'] + ' delivery was not confirmed'}\n\n"
                f"You have not been told about this enquiry. Open {_portal()} to read and answer it.")
        if await raise_issue(tenant, "alert_undelivered", row["id"], f"enquiry alert not delivered ({who})",
                             body, avoid=row["channel"], lead_id=row["lead_id"]):
            raised += 1
    return raised


async def sweep_unanswered() -> int:
    """Genuine enquiries still waiting for the owner past the threshold (tenant sla_minutes, else the default)."""
    settings = get_settings()
    raised = 0
    for record in await db.pool().fetch("SELECT * FROM tenants"):
        tenant = dict(record)
        tenant_sla = int(tenant.get("sla_minutes") or 0)
        minutes = tenant_sla or settings.owner_issue_unanswered_minutes
        if minutes <= 0:
            continue
        min_score = (
            int(tenant["sla_min_score"]) if tenant.get("sla_min_score") is not None else 70
        ) if tenant_sla > 0 else 0
        probe = {**tenant, "sla_minutes": minutes, "sla_min_score": min_score}
        for lead in await sla.overdue(probe, max_age_days=2):
            # Only enquiries the owner was actually alerted about are "genuine"; vendor mail never was.
            alerted = await db.pool().fetchval(
                "SELECT 1 FROM outbox WHERE tenant_id=$1 AND kind='owner_alert' AND lead_id=$2 AND dedupe_key LIKE 'enq:%'",
                tenant["id"], lead["id"])
            if not alerted:
                continue
            who = lead["name"] or lead["phone"] or lead["email"] or "a customer"
            kind = enquiry_alerts.label(lead['channel']).lower()
            article = "An" if kind[:1] in "aeiou" else "A"
            body = (f"{article} {kind} from {who} has had no reply "
                    f"for {lead['minutes_waiting']} minutes (target {minutes}).\n"
                    f"Phone: {lead['phone'] or '-'}  Email: {lead['email'] or '-'}\n\n"
                    f"Reply to them, then mark the enquiry contacted in {_portal()} and this stops.")
            send_at = outbox.next_allowed_send(ZoneInfo(tenant["timezone"] or "UTC"), datetime.now(timezone.utc))
            if await raise_issue(tenant, "unanswered", lead["id"], f"no reply yet to {who}", body,
                                 lead_id=lead["id"], send_at=send_at):
                await db.pool().execute("UPDATE leads SET sla_alerted_at = now() WHERE id = $1", lead["id"])
                raised += 1
    return raised


async def sweep_reply_failed() -> int:
    rows = await db.pool().fetch(
        """SELECT o.id, o.tenant_id, o.channel, o.to_addr, o.last_error, o.lead_id, l.name, l.email, l.phone
           FROM outbox o LEFT JOIN leads l ON l.id = o.lead_id
           WHERE o.kind = ANY($1::text[]) AND o.status='failed' AND o.created_at > now() - make_interval(hours => $2)
           ORDER BY o.id DESC LIMIT 20""", list(CUSTOMER_REPLY_KINDS), WINDOW_HOURS)
    raised = 0
    for row in rows:
        tenant = await _tenant(row["tenant_id"])
        if tenant is None:
            continue
        who = row["name"] or row["phone"] or row["email"] or row["to_addr"] or "a customer"
        phone = row["phone"] or (row["to_addr"] if row["channel"] == "sms" else "-")
        email = row["email"] or (row["to_addr"] if row["channel"] == "email" else "-")
        anchor = row["lead_id"] or f"outbox-{row['id']}"
        body = (f"Our reply to {who} by {row['channel']} could not be delivered.\n"
                f"Reason: {row['last_error'] or 'unknown'}\n\n"
                f"They have not heard back. Contact them directly: phone {phone}, email {email}. "
                f"Details in {_portal()}.")
        if await raise_issue(tenant, "reply_failed", anchor, f"reply to {who} failed", body, lead_id=row["lead_id"]):
            raised += 1
    return raised


async def sweep() -> int:
    total = 0
    for step in (sweep_undelivered, sweep_unanswered, sweep_reply_failed):
        try:
            total += await step()
        except Exception:  # noqa: BLE001 - one sweep failing must not stop the others
            log.exception("owner issue sweep %s failed", step.__name__)
    return total
