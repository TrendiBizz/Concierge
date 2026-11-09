"""Business-specific operational notices, atomically queued with CRM changes."""
from . import channel_authorization, db
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
        await runner.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,lead_id) "
            "VALUES($1,'owner_alert',$2,$3,$4,$5,$6,$7) "
            "ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
            tenant['id'], channel, recipient, subject, sms_body(subject, body) if channel == "sms" else body,
            dedupe + (':sms' if channel == 'sms' else ''), lead_id)
    return [channel for channel, _ in destinations]
