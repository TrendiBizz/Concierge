"""Optional enquirer acknowledgement, separate from operational owner notices."""
import json
from . import channel_authorization, db
from .contact import is_email, normalize_phone


async def request(tenant, args, ctx):
    if ctx.get('dry_run'):
        return {'ok': True, 'status': 'dry_run', 'note': 'No acknowledgement queued'}
    conversation_id = ctx.get('conversation_id')
    if not conversation_id:
        return {'ok': False, 'error': 'A saved conversation is required'}
    if args.get('requested') is False:
        await db.pool().execute("UPDATE conversations SET pending_ack='{\"declined\":true}'::jsonb WHERE tenant_id=$1 AND id=$2", tenant['id'], conversation_id)
        return {'ok': True, 'status': 'declined', 'note': 'No enquirer acknowledgement will be sent. The owner enquiry remains separate.'}
    if args.get('requested') is not True:
        return {'ok': False, 'error': 'Ask whether the enquirer wants an acknowledgement first'}
    channel = args.get('channel')
    if channel not in ('email', 'sms'):
        return {'ok': False, 'error': 'Ask which channel the enquirer wants: email or SMS'}
    recipient = str(args.get('recipient') or '').strip()
    recipient = recipient.lower() if channel == 'email' else normalize_phone(recipient)
    if not recipient or (channel == 'email' and not is_email(recipient)):
        return {'ok': False, 'error': 'A valid acknowledgement recipient is required'}
    key = {'channel': channel, 'recipient': recipient}
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow('SELECT pending_ack FROM conversations WHERE tenant_id=$1 AND id=$2 FOR UPDATE', tenant['id'], conversation_id)
            if not row:
                return {'ok': False, 'error': 'Conversation unavailable'}
            pending = row['pending_ack']
            if isinstance(pending, str):
                pending = json.loads(pending)
            if args.get('confirmed') is not True or pending != key:
                await conn.execute('UPDATE conversations SET pending_ack=$3::jsonb WHERE tenant_id=$1 AND id=$2', tenant['id'], conversation_id, json.dumps(key))
                return {'ok': False, 'needs_confirmation': True, 'read_back': f'Send an acknowledgement by {channel} to {recipient}? Wait for yes before confirming.'}
            if not await channel_authorization.is_authorized(tenant['id'], 'email_send' if channel == 'email' else 'sms_send'):
                return {'ok': False, 'error': 'Business has not authorized that delivery channel'}
            lead = await conn.fetchrow('SELECT id FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], conversation_id)
            if not lead:
                return {'ok': False, 'error': 'Save the enquiry before requesting an acknowledgement'}
            await conn.execute(
                "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,lead_id) VALUES($1,'enquirer_ack',$2,$3,$4,$5,$6,$7) "
                'ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING',
                tenant['id'], channel, recipient, 'Your enquiry with ' + tenant['name'],
                'Thank you for contacting ' + tenant['name'] + '. Your enquiry has been saved for the team to follow up.',
                f"enquirer-ack:{tenant['id']}:{conversation_id}:{channel}:{recipient}", lead['id'])
            await conn.execute('UPDATE conversations SET pending_ack=$3::jsonb WHERE tenant_id=$1 AND id=$2', tenant['id'], conversation_id, json.dumps(key))
    return {'ok': True, 'status': 'queued', 'recipient': recipient, 'note': 'Acknowledgement queued; receipt has not been verified. Device SMS requires Send confirmation.'}
