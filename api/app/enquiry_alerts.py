"""The ONE owner alert for a genuine customer enquiry, worded for the channel it arrived on.

Rules (Jo, 2026-11-21): a genuine enquiry produces exactly one alert per conversation / call / thread.
The inbound channel decides the wording; there are no copies on a second channel; robot, vendor and
verification mail produces no alert (it is logged). Problems with an enquiry (alert not delivered,
customer left waiting, reply failed) are a different thing and live in ``owner_issues``.

How "one" is enforced: every enquiry alert has the dedupe key ``enq:<tenant>:<thread>:<n>``. While the
alert is still waiting to go out, later turns of the same thread replace its text (the owner gets the
whole conversation, once). Once it has gone out, further turns of that thread make no new alert -- the
unanswered-enquiry notice covers a customer who is left waiting. A thread that has been quiet for
``owner_alert_reopen_hours`` and writes again is a new enquiry (``n`` + 1).
"""
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import automated_mail, db, owner_notifications
from .config import get_settings

log = logging.getLogger("concierge.enquiry_alerts")

# channel -> (subject lead-in, what the owner is looking at, what to do about it)
TEMPLATES = {
    "email": ("Email enquiry", "An email from a customer", "Reply to them by email."),
    "sms": ("Text message", "A text message from a customer", "Reply to them by text."),
    "phone": ("Phone call", "A phone call (voicemail / call summary)", "Ring them back."),
    "chat": ("Web chat", "A conversation on your website chat", "Follow up using the contact details below, if any."),
}
TEMPLATES["voice"] = TEMPLATES["phone"]
GENERIC = ("Enquiry", "A customer enquiry", "Follow up with them.")


def label(channel: str) -> str:
    return TEMPLATES.get(channel, GENERIC)[0]


def _snippet(text: str) -> str:
    for line in (text or "").splitlines():
        line = re.sub(r"(?i)^(enquirer|customer|concierge|caller):\s*", "", line.strip())
        if line:
            return re.sub(r"\s+", " ", line)[:60].rstrip()
    return ""


def subject_for(tenant: dict, channel: str, who: str, text: str, now=None) -> str:
    try:
        zone = ZoneInfo(tenant.get("timezone") or "UTC")
    except Exception:  # noqa: BLE001 - a bad timezone must not stop an alert
        zone = timezone.utc
    moment = (now or datetime.now(timezone.utc)).astimezone(zone)
    when = moment.strftime("%a ") + moment.strftime("%I:%M%p").lstrip("0").lower()
    snippet = _snippet(text)
    head = f"{label(channel)} for {tenant['name']}"
    if who:
        head += f" from {who}"
    return (f"{head}: {snippet} ({when})" if snippet else f"{head} ({when})")[:200]


def render(tenant: dict, channel: str, contact: dict, text: str) -> str:
    _, what, todo = TEMPLATES.get(channel, GENERIC)
    lines = [f"{what} for {tenant['name']}.", ""]
    for name, value in (("Name", contact.get("name")), ("Email", contact.get("email")), ("Phone", contact.get("phone"))):
        if value:
            lines.append(f"{name}: {value}")
    lines += ["", text.strip(), "", todo]
    return "\n".join(lines)


def _who(contact: dict) -> str:
    return contact.get("name") or contact.get("phone") or contact.get("email") or ""


async def notify(tenant: dict, channel: str, text: str, *, lead_id=None, conversation_id=None,
                 contact: dict | None = None, automated: bool = False, connection=None,
                 hold_seconds: float | None = None, finalize: bool = False, owner_phone: str | None = None):
    """Queue (or update) the single owner alert for this enquiry. Returns the outbox id, or None."""
    runner = connection or db.pool()
    contact = {k: (v or "").strip() for k, v in (contact or {}).items()}
    if lead_id is not None:
        lead = await runner.fetchrow("SELECT conversation_id,name,email,phone FROM leads WHERE id=$1", lead_id)
        if lead:
            conversation_id = conversation_id or lead["conversation_id"]
            for name in ("name", "email", "phone"):
                contact[name] = contact.get(name) or (lead[name] or "")
    thread = str(conversation_id) if conversation_id else (f"lead-{lead_id}" if lead_id else None)
    if thread is None:
        log.warning("enquiry alert on %s skipped: no conversation or lead to key it on", channel)
        return None
    clean = automated_mail.redact_security_codes(text or "")
    if automated or automated_mail.classify(contact.get("email", ""), "", body=clean) \
            or (channel == "email" and automated_mail.vendor_reason(contact.get("email", ""), "", clean)):
        log.info("no owner alert for non-genuine %s message (thread %s)", channel, thread)
        return None
    route = await owner_notifications.delivery_route(runner, tenant, owner_phone)
    if route is None:
        log.error("tenant %s has no reliable owner alert channel; enquiry %s is unannounced", tenant["id"], thread)
        return None
    kind, recipient = route
    settings = get_settings()
    debounce = max(0, settings.owner_alert_debounce_seconds)
    send_in = float(debounce if finalize or hold_seconds is None else max(debounce, hold_seconds))
    prefix = f"enq:{tenant['id']}:{thread}:"
    last = await runner.fetchrow(
        "SELECT id,status,send_at > now() AS held, "
        "created_at > now() - make_interval(hours => $3) AS recent "
        "FROM outbox WHERE tenant_id=$1 AND kind='owner_alert' AND dedupe_key LIKE $2 ORDER BY id DESC LIMIT 1",
        tenant["id"], prefix + "%", float(settings.owner_alert_reopen_hours))
    subject = subject_for(tenant, channel, _who(contact), clean)
    body = render(tenant, channel, contact, clean)
    if kind == "sms":
        body = owner_notifications.sms_body(subject, body)
    if last and last["recent"]:
        if last["status"] == "pending" and last["held"]:
            await runner.execute(
                "UPDATE outbox SET body=$2, subject=$3, send_at=CASE WHEN $4 THEN "
                "LEAST(send_at, now() + make_interval(secs => $5)) ELSE send_at END WHERE id=$1 AND status='pending'",
                last["id"], body, subject, finalize, float(debounce))
        return last["id"]          # already sent or on its way: this enquiry has its one alert
    seq = 1 + int(await runner.fetchval(
        "SELECT count(*) FROM outbox WHERE tenant_id=$1 AND kind='owner_alert' AND dedupe_key LIKE $2",
        tenant["id"], prefix + "%"))
    new_id = await runner.fetchval(
        "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,lead_id,send_at) "
        "VALUES($1,'owner_alert',$2,$3,$4,$5,$6,$7, now() + make_interval(secs => $8)) "
        "ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING RETURNING id",
        tenant["id"], kind, recipient, subject, body, f"{prefix}{seq}", lead_id, send_in)
    if new_id is not None:
        owner_notifications.spawn_push(tenant, subject, body, f"{prefix}{seq}")
    return new_id
