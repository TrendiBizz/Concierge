"""What happens after a lead is captured or an appointment changes: owner alerts, texts, reminders, reviews, webhooks."""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import events, outbox
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


def _sms_target(tenant: dict, phone: str, consent: bool) -> str | None:
    """A phone number we may text: SMS enabled for the client, visitor consented, number valid."""
    if not (tenant.get("sms_enabled") and consent and phone):
        return None
    return normalize_phone(phone, get_settings().default_country_code)


async def _owner_alert(tenant: dict, subject: str, body: str, dedupe: str) -> None:
    if tenant.get("notify_email") and is_email(tenant["notify_email"]):
        await outbox.enqueue(
            tenant["id"], "owner_alert", "email", tenant["notify_email"], body,
            subject=subject, dedupe_key=dedupe,
        )


async def on_lead_created(tenant: dict, lead: dict) -> None:
    events.emit(tenant, "lead.created", lead_id=lead["id"], lead=events.lead_view(lead))

    contact = lead["phone"] or lead["email"] or "-"
    await _owner_alert(
        tenant,
        f"New lead for {tenant['name']}: {lead['name'] or contact}",
        f"Name: {lead['name']}\nPhone: {lead['phone']}\nEmail: {lead['email']}\n"
        f"Channel: {lead['channel']}\nPage: {lead.get('page_url') or '-'}\n\n{lead['message']}\n",
        f"lead:{lead['id']}:owner",
    )

    # Speed-to-lead text. If they texted us first, the conversation already is the reply.
    to = _sms_target(tenant, lead["phone"], lead["consent_contact"])
    if to and lead["channel"] != "sms":
        template = tenant.get("lead_sms_template") or (
            "Hi {first}, thanks for reaching out to {business}! A team member will follow up shortly. "
            "Reply STOP to opt out."
        )
        text = template.format(first=_first_name(lead["name"]), name=lead["name"], business=tenant["name"])
        await outbox.enqueue(
            tenant["id"], "speed_to_lead", "sms", to, text,
            dedupe_key=f"lead:{lead['id']}:sms", lead_id=lead["id"],
        )


async def on_appointment_booked(tenant: dict, appt: dict, lead: dict | None) -> None:
    events.emit(
        tenant, "appointment.booked",
        appointment=events.appointment_view(appt, tenant["timezone"]),
        lead=events.lead_view(lead) if lead else None,
    )
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
    email_to = appt["email"] if is_email(appt["email"]) else None
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
