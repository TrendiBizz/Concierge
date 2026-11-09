"""Durable CRM capture at authenticated channel ingress, independent of AI replies."""
import hashlib

from . import automation, db, owner_notifications


async def capture(tenant: dict, channel: str, source: str, message: str, *,
                  conversation_id=None, email: str = "", phone: str = "",
                  consent_contact: bool = False) -> dict:
    if channel not in ("email", "sms", "phone", "chat") or not source:
        raise ValueError("Authenticated channel event required")
    key = hashlib.sha256(source.encode()).hexdigest()
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                               f"enquiry:{tenant['id']}:{channel}:{key}")
            row = await conn.fetchrow(
                "SELECT * FROM leads WHERE tenant_id=$1 AND channel=$2 AND source_key=$3",
                tenant["id"], channel, key)
            created = row is None
            if created:
                row = await conn.fetchrow(
                    "INSERT INTO leads(tenant_id,conversation_id,email,phone,message,channel,source_key,consent_contact) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *",
                    tenant["id"], conversation_id, email[:200], phone[:40], message[:1000],
                    channel, key, consent_contact)
            elif conversation_id or message:
                row = await conn.fetchrow(
                    "UPDATE leads SET conversation_id=COALESCE(conversation_id,$2), "
                    "message=CASE WHEN $3<>'' THEN $3 ELSE message END, updated_at=now() "
                    "WHERE id=$1 RETURNING *", row["id"], conversation_id, message[:1000])
            original_key = hashlib.sha256((source + '\0' + message).encode()).hexdigest()
            await conn.execute(
                'INSERT INTO enquiry_sources(tenant_id,channel,source_key,lead_id,original_text) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',
                tenant['id'], channel, original_key, row['id'], message[:30000])
            await owner_notifications.queue(
                tenant, channel.title() + ' enquiry for ' + tenant['name'],
                f'Channel: {channel}\nEmail: {email}\nPhone: {phone}\n\n' + message[:30000],
                f"enquiry-original:{tenant['id']}:{channel}:{original_key}", lead_id=row['id'], connection=conn)
    lead = dict(row)
    if created:
        await automation.on_lead_created(tenant, {**lead, "_owner_notice_queued": True})
    return lead
