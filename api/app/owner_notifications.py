"""Owner notices: the delivery-channel policy, plus one-off operational notices (payment, take-over, ...).

Customer ENQUIRY alerts live in ``enquiry_alerts``; problems with them live in ``owner_issues``.
"""
import asyncio
from . import automated_mail, channel_authorization, db, webpush
from .contact import is_email, normalize_phone
from .config import get_settings
import re


def sms_body(subject, body):
    body = automated_mail.redact_security_codes(body or "")
    subject = automated_mail.redact_security_codes(subject or "")
    if len(body) <= 1400:
        return body
    links = re.findall(r"https?://[^\s]+/recordings/shared/[^\s]+", body)
    suffix = "\nFull original conversation in your private portal: " + get_settings().public_base_url.rstrip("/") + "/owner-ui"
    if links:
        suffix += "\nRecording: " + links[-1]
    return subject[:160] + "\n" + body[:max(0, 1400-len(suffix)-162)] + suffix


# Owner SMS goes through a Mac that needs a human to press Send within 60 seconds (see
# docs/OWNER_ALERT_SMS.md). After this many unconfirmed texts in a row, owner SMS is not "reliably
# deliverable" until the probe interval has passed.
SMS_BREAKER_FAILURES = 3
SMS_BREAKER_PROBE_HOURS = 2


async def sms_unconfirmable(runner, tenant_id) -> bool:
    """True when the last few owner texts all went unconfirmed and the probe interval has not passed."""
    rows = await runner.fetch(
        "SELECT status,last_error,created_at > now() - make_interval(hours => $3) AS recent "
        "FROM outbox WHERE tenant_id=$1 AND kind IN ('owner_alert','owner_issue') AND channel='sms' "
        "AND status IN ('sent','failed','cancelled') ORDER BY id DESC LIMIT $2",
        tenant_id, SMS_BREAKER_FAILURES, SMS_BREAKER_PROBE_HOURS)
    return (len(rows) == SMS_BREAKER_FAILURES and rows[0]["recent"]
            and all(r["status"] != "sent" and "did not confirm" in (r["last_error"] or "") for r in rows))


async def sms_reliable(runner, tenant, phone=None) -> tuple | None:
    phone = normalize_phone(phone or tenant.get("notify_phone", ""))
    if (phone and tenant.get("sms_enabled")
            and await channel_authorization.is_authorized(tenant["id"], "sms_send")
            and not await sms_unconfirmable(runner, tenant["id"])):
        return ("sms", phone)
    return None


async def delivery_route(runner, tenant, owner_phone=None, *, avoid=None) -> tuple | None:
    """Choose the ONE channel an owner notice goes out on. Email is primary. Owner SMS is used only when
    there is no usable email address and the phone connector is currently confirming texts.
    ``avoid`` excludes a channel that just failed (used by issue notices)."""
    if avoid != "email" and is_email(tenant.get("notify_email", "")):
        return ("email", tenant["notify_email"])
    if avoid != "sms":
        return await sms_reliable(runner, tenant, owner_phone)
    return None


async def queue(tenant, subject, body, dedupe, *, connection=None, **_ignored):
    """A one-off operational notice to the owner (payment received, take-over, appointment booked...).

    One channel, chosen by ``delivery_route``; never a copy on a second channel; deduped on ``dedupe``.
    Customer enquiries do NOT use this: see ``enquiry_alerts.notify``.
    """
    subject = automated_mail.redact_security_codes(subject or "")
    body = automated_mail.redact_security_codes(body or "")
    runner = connection or db.pool()
    route = await delivery_route(runner, tenant)
    if route is None:
        return []
    channel, recipient = route
    text = sms_body(subject, body) if channel == "sms" else body
    await runner.execute(
        "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key) "
        "VALUES($1,'owner_alert',$2,$3,$4,$5,$6) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
        tenant["id"], channel, recipient, subject, text, dedupe)
    spawn_push(tenant, subject, body, dedupe)
    return [channel]


_push_tasks: set = set()


def spawn_push(tenant, subject, body, dedupe) -> None:
    """Also push the alert to the owner's devices, in the background so it never delays or fails the alert."""
    try:
        task = asyncio.get_running_loop().create_task(webpush.notify(tenant, subject, body, dedupe))
        _push_tasks.add(task)
        task.add_done_callback(_push_tasks.discard)
    except Exception:  # noqa: BLE001 - no running loop (a script or a test): there is nothing to push from
        pass
