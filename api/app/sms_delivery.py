"""Durable SMS submission and monotonic delivery receipts, scoped to one outbox row."""
from . import db


async def begin(outbox_id: int, tenant_id, provider: str) -> bool:
    # Commit before the HTTP call. A crash after provider acceptance must never auto-resend.
    result = await db.pool().execute(
        "UPDATE outbox SET sms_provider=$3, sms_delivery_status='submitting', "
        "status='awaiting_receipt', claimed_at=now() "
        "WHERE id=$1 AND tenant_id=$2 AND channel='sms' AND status='sending' "
        "AND sms_provider IS NULL", outbox_id, tenant_id, provider)
    return result == "UPDATE 1"


async def accepted(outbox_id: int, provider: str, message_id: str) -> None:
    # A fast callback can arrive before the sender's response. Do not overwrite its state.
    await db.pool().execute(
        "UPDATE outbox SET sms_provider_id=COALESCE(sms_provider_id,NULLIF($3,'')), "
        "sms_delivery_status=CASE WHEN sms_delivery_status='submitting' THEN 'queued' "
        "ELSE sms_delivery_status END WHERE id=$1 AND sms_provider=$2 "
        "AND (sms_provider_id IS NULL OR sms_provider_id=NULLIF($3,''))",
        outbox_id, provider, message_id)


async def twilio_receipt(outbox_id: int, params: dict[str, str]) -> bool:
    sid = params.get("MessageSid", "")
    state = params.get("MessageStatus", "")
    if not sid or len(sid) > 100 or state not in {
        "accepted", "queued", "sending", "sent", "delivered", "undelivered", "failed", "canceled",
    }:
        return False
    # Only delivered means confirmed. 'sent' means handed to the downstream carrier.
    final = "sent" if state == "delivered" else (
        "failed" if state in {"undelivered", "failed", "canceled"} else "awaiting_receipt")
    rank = {"accepted": 1, "queued": 2, "sending": 3, "sent": 4}.get(state, 5)
    row = await db.pool().fetchrow(
        "UPDATE outbox SET sms_provider_id=$2, sms_delivery_status=$3, status=$4, "
        "sent_at=CASE WHEN $3='delivered' THEN COALESCE(sent_at,now()) ELSE sent_at END, "
        "last_error=CASE WHEN $4='failed' THEN 'Carrier reported SMS delivery failure' ELSE '' END "
        "WHERE id=$1 AND channel='sms' AND sms_provider='twilio' AND to_addr=$5 "
        "AND (sms_provider_id IS NULL OR sms_provider_id=$2) "
        "AND status IN ('awaiting_receipt','held') "
        "AND $6 >= CASE sms_delivery_status WHEN 'accepted' THEN 1 WHEN 'queued' THEN 2 "
        "WHEN 'sending' THEN 3 WHEN 'sent' THEN 4 ELSE 0 END RETURNING id",
        outbox_id, sid, state, final, params.get("To", ""), rank)
    # Duplicate / reordered callbacks for an already terminal row are harmless.
    if row:
        return True
    return bool(await db.pool().fetchval(
        "SELECT 1 FROM outbox WHERE id=$1 AND channel='sms' AND sms_provider='twilio' "
        "AND sms_provider_id=$2 AND to_addr=$3 AND status IN ('sent','failed','awaiting_receipt','held')",
        outbox_id, sid, params.get("To", "")))


async def smsgate_receipt(tenant_id, event: str, payload: dict) -> bool:
    """Apply signed smsgate delivery callbacks (sms:sent / sms:delivered / sms:failed)."""
    msg_id = str(payload.get("messageId") or payload.get("id") or "").strip()
    if not msg_id or len(msg_id) > 100:
        return False
    state_map = {"sms:sent": ("sent", "awaiting_receipt", 4),
                 "sms:delivered": ("delivered", "sent", 5),
                 "sms:failed": ("failed", "failed", 5)}
    mapped = state_map.get(event)
    if not mapped:
        return False
    state, final, rank = mapped
    row = await db.pool().fetchrow(
        "UPDATE outbox SET sms_delivery_status=$3, status=$4, "
        "sent_at=CASE WHEN $3='delivered' THEN COALESCE(sent_at,now()) ELSE sent_at END, "
        "last_error=CASE WHEN $4='failed' THEN 'SMS gateway reported delivery failure' ELSE '' END "
        "WHERE tenant_id=$1 AND channel='sms' AND sms_provider='smsgate' AND sms_provider_id=$2 "
        "AND status IN ('awaiting_receipt','held') "
        "AND $5 >= CASE sms_delivery_status WHEN 'accepted' THEN 1 WHEN 'queued' THEN 2 "
        "WHEN 'sending' THEN 3 WHEN 'sent' THEN 4 ELSE 0 END RETURNING id",
        tenant_id, msg_id, state, final, rank,
    )
    return bool(row)


async def reconcile() -> None:
    # Missing DLRs are unknown, never 'delivered' and never silently retried.
    await db.pool().execute(
        "UPDATE outbox SET status='held', last_error='Carrier delivery unconfirmed; reconcile before retry' "
        "WHERE channel='sms' AND sms_provider IN ('hero','smsgate','twilio') "
        "AND status='awaiting_receipt' AND claimed_at < now()-interval '24 hours'")
