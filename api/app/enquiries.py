"""Durable CRM capture at authenticated channel ingress, independent of AI replies."""
import hashlib

from . import automation, casetimeline, db, owner_notifications, tasks


async def capture(tenant: dict, channel: str, source: str, message: str, *,
                  conversation_id=None, email: str = "", phone: str = "",
                  consent_contact: bool = False) -> dict:
    if channel not in ("email", "sms", "phone", "chat") or not source:
        raise ValueError("Authenticated channel event required")
    key = hashlib.sha256(source.encode()).hexdigest()

    # Resolve the customer's unified case BEFORE the capture transaction, so a customer who has
    # already written on another channel is recognised as the same person. A case is a customer,
    # not a conversation: this is what stops email/SMS/call from becoming three unrelated records.
    # Reconcile, not merely ensure: if this customer already exists under their OTHER identifier
    # (an email case from last week, a phone case from a call), the two are merged rather than
    # leaving the owner with the same person recorded twice.
    case = await casetimeline.reconcile(
        tenant["id"], phone=phone, email=email,
        default_cc=casetimeline.tenant_country_code(tenant),
        # The channel that carried the identifier is the source: an email case is captured from
        # email, a call from caller ID. This is what lets the owner tell an auto-captured address
        # from one they typed in themselves.
        source=channel,
    )
    case_id = case["id"] if case else None

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
                    "INSERT INTO leads(tenant_id,conversation_id,email,phone,message,channel,source_key,consent_contact,case_id) "
                    "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",
                    tenant["id"], conversation_id, email[:200], phone[:40], message[:1000],
                    channel, key, consent_contact, case_id)
            elif conversation_id or message:
                row = await conn.fetchrow(
                    "UPDATE leads SET conversation_id=COALESCE(conversation_id,$2), "
                    "message=CASE WHEN $3<>'' THEN $3 ELSE message END, "
                    "case_id=COALESCE(case_id,$4), updated_at=now() "
                    "WHERE id=$1 RETURNING *", row["id"], conversation_id, message[:1000], case_id)
            original_key = hashlib.sha256((source + '\0' + message).encode()).hexdigest()
            await conn.execute(
                'INSERT INTO enquiry_sources(tenant_id,channel,source_key,lead_id,original_text) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',
                tenant['id'], channel, original_key, row['id'], message[:30000])
            await owner_notifications.queue(
                tenant, channel.title() + ' enquiry for ' + tenant['name'],
                f'Channel: {channel}\nEmail: {email}\nPhone: {phone}\n\n' + message[:30000],
                f"enquiry-original:{tenant['id']}:{channel}:{original_key}", lead_id=row['id'], connection=conn)

    # Record the message on the unified timeline. Idempotent on (tenant, channel, source_key), so a
    # retried provider webhook collapses instead of duplicating the customer's history.
    if case_id:
        await casetimeline.record(
            tenant["id"], case_key=case["case_key"], channel=channel, direction="inbound",
            source_key=original_key, body=message,
        )

    lead = dict(row)
    message_key = f"{channel}:{original_key}"
    if created:
        await automation.on_lead_created(
            tenant, {**lead, "_owner_notice_queued": True}, message_key=message_key)
    else:
        # A second message on the same conversation is fresh work, while a replay is not.
        await tasks.create_follow_up(tenant, lead, message_key=message_key)
    return lead
