"""Business-specific operational notices, atomically queued with CRM changes."""
import asyncio
from . import channel_authorization, db, webpush
from .contact import is_email, normalize_phone
from .config import get_settings
import re


def sms_body(subject, body):
    if len(body) <= 1400:
        return body
    links = re.findall(r"https?://[^\s]+/recordings/shared/[^\s]+", body)
    suffix = "\nFull original conversation in your private portal: " + get_settings().public_base_url.rstrip("/") + "/owner-ui"
    if links:
        suffix += "\nRecording: " + links[-1]
    return subject[:160] + "\n" + body[:max(0, 1400-len(suffix)-162)] + suffix


async def queue(tenant, subject, body, dedupe, *, lead_id=None, connection=None):
    runner = connection or db.pool()
    destinations = []
    if is_email(tenant.get('notify_email', '')):
        destinations.append(('email', tenant['notify_email']))
    phone = normalize_phone(tenant.get('notify_phone', ''))
    if phone and tenant.get('sms_enabled') and await channel_authorization.is_authorized(tenant['id'], 'sms_send'):
        destinations.append(('sms', phone))
    for channel, recipient in destinations:
        # Coalesce rapid alerts for the same lead on the same channel.
        #
        # Deduplication alone cannot do this: the caller's key includes the message text, so that two
        # genuinely different enquiries are not collapsed. The consequence is one alert per
        # conversation turn -- a 30-turn enquiry produced 54 texts to the owner. Suppressing a recent
        # UNDELIVERED alert for the same lead keeps the owner informed without turning a conversation
        # into a stream of messages. The earlier row still goes out, carrying the dialogue as it stood;
        # anything after the interval is queued normally, so no enquiry is ever silently dropped.
        if lead_id is not None:
            interval = get_settings().owner_alert_min_interval_seconds
            if interval > 0:
                # The initial outbox status is the schema default 'pending' (not 'queued').
                # A first version of this guard matched only ('queued','sending'), so it never
                # fired in production and a 30-turn conversation still queued 30 alerts per
                # channel. Treat every undelivered state as in-flight.
                recent = await runner.fetchval(
                    "SELECT 1 FROM outbox WHERE tenant_id=$1 AND kind='owner_alert' AND channel=$2 "
                    "AND lead_id=$3 AND created_at > now() - make_interval(secs => $4) "
                    "AND status IN ('pending','sending','awaiting_receipt') LIMIT 1",
                    tenant['id'], channel, lead_id, interval)
                if recent:
                    continue
        await runner.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,lead_id) "
            "VALUES($1,'owner_alert',$2,$3,$4,$5,$6,$7) "
            "ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
            tenant['id'], channel, recipient, subject, sms_body(subject, body) if channel == "sms" else body,
            dedupe + (':sms' if channel == 'sms' else ''), lead_id)
    _spawn_push(tenant, subject, body, dedupe)
    return [channel for channel, _ in destinations]


_push_tasks: set = set()


def _spawn_push(tenant, subject, body, dedupe) -> None:
    """Also push the alert to the owner's devices, in the background so it never delays or fails the alert."""
    try:
        task = asyncio.get_running_loop().create_task(webpush.notify(tenant, subject, body, dedupe))
        _push_tasks.add(task)
        task.add_done_callback(_push_tasks.discard)
    except Exception:  # noqa: BLE001 - no running loop (a script or a test): there is nothing to push from
        pass
