"""What happens after a lead is captured or an appointment changes: owner alerts, texts, reminders, reviews, webhooks."""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import events, outbox, sales, scoring, tasks
from .config import get_settings
from .contact import is_email, normalize_phone

log = logging.getLogger("concierge.automation")


def _first_name(name: str) -> str:
    return (name or "").strip().split(" ")[0] or "there"


def fmt_local(tenant: dict, moment: datetime) -> str:
    local = moment.astimezone(ZoneInfo(tenant["timezone"]))
    hour12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{local:%A, %B} {local.day} at {hour12}:{local:%M} {suffix} {local:%Z}"


def _score_tag(lead: dict) -> str:
    label = lead.get("score_label")
    return f"[{label.upper()}] " if label in ("hot", "warm") else ""


def _score_lines(lead: dict) -> str:
    if lead.get("score") is None:
        return ""
    why = "; ".join(scoring.reasons_of(lead)) or "-"
    return f"Score: {lead['score']}/100 ({lead.get('score_label')})\nWhy: {why}\n\n"


def _sms_target(tenant: dict, phone: str, consent: bool) -> str | None:
    """A phone number we may text: SMS enabled for the client, visitor consented, number valid."""
    if not (tenant.get("sms_enabled") and consent and phone):
        return None
    return normalize_phone(phone, get_settings().default_country_code)


async def _owner_alert(tenant: dict, subject: str, body: str, dedupe: str) -> None:
    from . import owner_notifications
    await owner_notifications.queue(tenant, subject, body, dedupe)


async def on_lead_created(tenant: dict, lead: dict) -> None:
    try:
        lead = await scoring.apply(lead, weights=scoring.weights_for(tenant))
    except Exception:  # scoring must never stop a lead from being handled
        log.exception("lead scoring failed for %s", lead.get("id"))
    try:
        await tasks.create_follow_up(tenant, lead)  # one to-do per new lead, completes itself when answered
    except Exception:
        log.exception("follow-up to-do failed for %s", lead.get("id"))
    events.emit(tenant, "lead.created", lead_id=lead["id"], lead=events.lead_view(lead))
    try:
        await events.queue_twenty(tenant,"lead.created",str(lead["id"]),
                                 {"lead":events.lead_view(lead)})
    except Exception:
        log.exception("Could not persist Twenty CRM delivery for lead %s",lead["id"])

    contact = lead["phone"] or lead["email"] or "-"
    if not lead.get("_owner_notice_queued"):
        await _owner_alert(
            tenant,
            f"{_score_tag(lead)}New lead for {tenant['name']}: {lead['name'] or contact}",
            f"{_score_lines(lead)}Name: {lead['name']}\nPhone: {lead['phone']}\nEmail: {lead['email']}\n"
            f"Channel: {lead['channel']}\nPage: {lead.get('page_url') or '-'}\n\n{lead['message']}\n",
            f"lead:{lead['id']}:owner",
        )

    await lead_followup(tenant, lead)


async def lead_followup(tenant: dict, lead: dict) -> None:
    # Contact consent permits follow-up, but is not a request for an acknowledgement.
    # The explicit request_enquiry_acknowledgement tool queues the visitor's copy.
    return


async def on_appointment_booked(tenant: dict, appt: dict, lead: dict | None) -> None:
    if lead:
        try:
            lead = await scoring.apply(lead, booked=True, weights=scoring.weights_for(tenant))
        except Exception:
            log.exception("lead scoring failed for %s", lead.get("id"))
    if lead:  # a booking is a deal that has reached the 'booked' stage
        try:
            await sales.change_status(lead["id"], "booked")
        except Exception:
            log.exception("could not move lead to booked: %s", lead.get("id"))
    events.emit(
        tenant, "appointment.booked",
        appointment=events.appointment_view(appt, tenant["timezone"]),
        lead=events.lead_view(lead) if lead else None,
    )
    try:
        await events.queue_twenty(tenant,"appointment.booked",str(appt["id"]),{
            "appointment":events.appointment_view(appt,tenant["timezone"]),
            "lead":events.lead_view(lead) if lead else None,
        })
    except Exception:
        log.exception("Could not persist Twenty CRM delivery for booking %s",appt["id"])
    when = fmt_local(tenant, appt["starts_at"])
    await _owner_alert(
        tenant,
        f"New appointment for {tenant['name']}: {appt['name']} - {when}",
        f"{appt['name']} booked {when}.\nPhone: {appt['phone']}\nEmail: {appt['email']}\n"
        f"Notes: {appt['notes']}\n",
        f"appt:{appt['id']}:owner",
    )

    now = datetime.now(timezone.utc)
    sms_to = _sms_target(tenant, appt["phone"], appt["consent_contact"])
    email_to = appt["email"] if appt["consent_contact"] and is_email(appt["email"]) else None
    first = _first_name(appt["name"])

    # Confirmation + two reminders, on whichever channels we are allowed to use.
    plan = [("confirm", now, f"Hi {first}, you're booked with {tenant['name']} for {when}."),
            ("rem24", appt["starts_at"] - timedelta(hours=24), f"Reminder: your appointment with {tenant['name']} is tomorrow, {when}."),
            ("rem2", appt["starts_at"] - timedelta(hours=2), f"Reminder: your appointment with {tenant['name']} is today, {when}.")]
    for tag, send_at, text in plan:
        if tag != "confirm" and send_at <= now:
            continue
        if sms_to:
            await outbox.enqueue(
                tenant["id"], f"appt_{tag}", "sms", sms_to, f"{text} Reply STOP to opt out.",
                send_at=send_at, dedupe_key=f"appt:{appt['id']}:{tag}:sms", appointment_id=appt["id"],
            )
        if email_to:
            await outbox.enqueue(
                tenant["id"], f"appt_{tag}", "email", email_to, text,
                subject=f"Your appointment with {tenant['name']}", send_at=send_at,
                dedupe_key=f"appt:{appt['id']}:{tag}:email", appointment_id=appt["id"],
            )


async def on_appointment_status(tenant: dict, appt: dict, status: str) -> None:
    events.emit(tenant, f"appointment.{status}", appointment=events.appointment_view(appt, tenant["timezone"]))

    if status in ("cancelled", "no_show"):
        await outbox.cancel_for_appointment(appt["id"])
        return

    if status == "completed" and tenant.get("review_url"):
        send_at = datetime.now(timezone.utc) + timedelta(hours=1)
        first = _first_name(appt["name"])
        text = (f"Thanks for visiting {tenant['name']}, {first}! If we did a good job, would you leave a "
                f"quick review? {tenant['review_url']}")
        sms_to = _sms_target(tenant, appt["phone"], appt["consent_contact"])
        if sms_to:
            await outbox.enqueue(
                tenant["id"], "review_request", "sms", sms_to, f"{text} Reply STOP to opt out.",
                send_at=send_at, dedupe_key=f"appt:{appt['id']}:review:sms", appointment_id=appt["id"],
            )
        if is_email(appt["email"]):
            await outbox.enqueue(
                tenant["id"], "review_request", "email", appt["email"], text,
                subject=f"How was your visit to {tenant['name']}?", send_at=send_at,
                dedupe_key=f"appt:{appt['id']}:review:email", appointment_id=appt["id"],
            )
