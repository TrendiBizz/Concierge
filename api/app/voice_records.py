"""Private recordings and completed voice enquiries, using existing storage and outbox."""
import io
import wave
import hashlib
import json
import secrets

from fastapi import HTTPException

from . import channel_authorization, convo, db, outbox, events
from .config import get_settings

MAX_AUDIO = 12 * 1024 * 1024
TENANT_AUDIO_QUOTA = 100 * 1024 * 1024
MIME_TYPES = {'audio/webm': b'\x1aE\xdf\xa3', 'audio/ogg': b'OggS', 'audio/mp4': None, 'audio/wav': b'RIFF'}


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def start(tenant, session_id, *, record=False, channel='voice'):
    if record and not (get_settings().voice_recording_enabled and
                       await channel_authorization.is_authorized(tenant['id'], 'call_recording')):
        raise HTTPException(403, 'Recording is not enabled for this business')
    await db.pool().execute("DELETE FROM voice_recordings WHERE tenant_id=$1 AND created_at<now()-interval '30 days'", tenant['id'])
    conversation = await convo.get_or_create(tenant, session_id, channel, None, None)
    token = secrets.token_urlsafe(32)
    row = await db.pool().fetchrow(
        "INSERT INTO voice_sessions(tenant_id,conversation_id,token_hash,recording_consent) "
        "VALUES($1,$2,$3,$4) RETURNING id", tenant['id'], conversation, digest(token), record)
    return {'id': str(row['id']), 'token': token, 'recording': record}


async def authenticate(session_id, token):
    if len(token) > 200 or len(token) < 32:
        raise HTTPException(403, 'Invalid voice session')
    row = await db.pool().fetchrow(
        "SELECT * FROM voice_sessions WHERE id=$1 AND token_hash=$2 AND expires_at>now()",
        session_id, digest(token))
    if not row:
        raise HTTPException(403, 'Voice session expired or unavailable')
    return dict(row)


def audio_type(content_type, body):
    mime = content_type.split(';', 1)[0].strip().lower()
    if mime not in MIME_TYPES or len(body) < 16:
        raise HTTPException(415, 'Unsupported audio recording')
    valid = (body[4:8] == b'ftyp') if mime == 'audio/mp4' else body.startswith(MIME_TYPES[mime])
    if not valid:
        raise HTTPException(415, 'Audio container does not match its type')
    if mime == 'audio/wav':
        try:
            with wave.open(io.BytesIO(body), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 8000):
                    raise ValueError('Unsupported telephone PCM')
                frames = audio.getnframes()
                if frames > 600*8000 or len(audio.readframes(frames)) != frames*2:
                    raise ValueError('Truncated or excessive telephone audio')
        except (wave.Error, EOFError, ValueError):
            raise HTTPException(415, 'Invalid telephone recording')
    return mime


async def store_audio(session, body, content_type):
    if not (session['recording_consent'] and get_settings().voice_recording_enabled and await channel_authorization.is_authorized(session['tenant_id'], 'call_recording')):
        raise HTTPException(403, 'Recording was not requested for this conversation')
    if len(body) > MAX_AUDIO:
        raise HTTPException(413, 'Recording exceeds the size limit')
    mime = audio_type(content_type, body)
    async with db.pool().acquire() as c:
        async with c.transaction():
            # Serialise quota and duplicate checks for this business.
            await c.execute('SELECT id FROM tenants WHERE id=$1 FOR UPDATE', session['tenant_id'])
            saved = await c.fetchrow('SELECT mime_type,sha256 FROM voice_recordings WHERE session_id=$1', session['id'])
            sha = hashlib.sha256(body).hexdigest()
            if saved:
                if saved['sha256'] != sha:
                    raise HTTPException(409, 'A different recording is already saved for this session')
                return {'ok': True, 'duplicate': True}
            used = await c.fetchval('SELECT COALESCE(sum(octet_length(audio)),0) FROM voice_recordings WHERE tenant_id=$1', session['tenant_id'])
            if used + len(body) > TENANT_AUDIO_QUOTA:
                raise HTTPException(409, 'Business recording storage is full')
            await c.execute(
                'INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256) VALUES($1,$2,$3,$4,$5,$6)',
                session['id'], session['tenant_id'], session['conversation_id'], mime, body, sha)
    return {'ok': True}


async def finish(session, tenant):
    """One CRM enquiry and one owner completion notice; retrying is safe."""
    async with db.pool().acquire() as c:
        async with c.transaction():
            current = await c.fetchrow('SELECT finalized_at,delivery_request FROM voice_sessions WHERE id=$1 FOR UPDATE', session['id'])
            if current['finalized_at']:
                result = {'ok': True, 'duplicate': True}
            else:
                result = await _finish_enquiry(c, session, tenant)
    return await complete_delivery(session, tenant, current['delivery_request'], result)


async def complete_delivery(session, tenant, request, result):
    if request and not result.get('empty'):
        if isinstance(request, str):
            request = json.loads(request)
        lead_id = await db.pool().fetchval('SELECT id FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], session['conversation_id'])
        try:
            result['delivery'] = await deliver(tenant, lead_id, **request, request_id=session['id'], session_id=session['id'])
        except HTTPException as exc:
            result['delivery'] = {'status': 'not_queued', 'note': exc.detail}
    return result


async def _finish_enquiry(c, session, tenant):
    """Run under the session row lock, in the caller's transaction."""
    turns = await c.fetch("SELECT role,content FROM messages WHERE conversation_id=$1 AND role IN ('user','assistant') ORDER BY id LIMIT 300", session['conversation_id'])
    caller = '\n'.join(r['content'] for r in turns if r['role'] == 'user').strip()
    if not caller:
        return {'ok': True, 'empty': True}
    # An earlier capture_lead tool may already have created the enquiry.
    lead = await c.fetchrow('SELECT * FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], session['conversation_id'])
    if not lead:
        lead = await c.fetchrow(
            "INSERT INTO leads(tenant_id,conversation_id,channel,source_key,message) VALUES($1,$2,'voice',$3,$4) RETURNING *",
            tenant['id'], session['conversation_id'], 'voice:'+str(session['id']), caller[:1000])
    transcript = '\n\n'.join(('Customer: ' if r['role']=='user' else 'Concierge: ')+r['content'] for r in turns)[:24000]
    if tenant.get('notify_email'):
        # Write the notice in this same transaction; no external send here.
        await c.execute(
            "INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key,lead_id) "
            "VALUES($1,'owner_alert','email',$2,$3,$4,$5,$6) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
            tenant['id'], tenant['notify_email'], 'Voice enquiry for '+tenant['name'],
            transcript+'\n\nOpen the enquiry in your Concierge CRM for its saved transcript and any recording.',
            'voice-finished:'+str(session['id']), lead['id'])
    await events.queue_twenty(tenant, 'voice.completed', str(session['id']), {'lead': {**dict(lead), 'message': transcript[:1400]}}, connection=c)
    await c.execute('UPDATE voice_sessions SET finalized_at=now() WHERE id=$1', session['id'])
    return {'ok': True, 'lead_id': str(lead['id'])}


async def request_delivery(session, tenant, *, channel, content, confirmed):
    """Remember the caller's choice; finalization sends only after storage succeeds."""
    if confirmed is not True:
        raise HTTPException(409, 'Read back the recipient and format, then ask the caller to confirm')
    if channel not in ('sms', 'email') or content not in ('text', 'recording'):
        raise HTTPException(422, 'Choose text or recording, by SMS or email')
    if content == 'recording' and not session['recording_consent']:
        raise HTTPException(409, 'No recording was requested for this conversation. Offer a text copy instead')
    if not await channel_authorization.is_authorized(tenant['id'], 'sms_send' if channel == 'sms' else 'email_send'):
        raise HTTPException(403, 'Business has not authorized this delivery channel')
    lead = await db.pool().fetchrow('SELECT phone,email,consent_contact FROM leads WHERE tenant_id=$1 AND conversation_id=$2 ORDER BY created_at LIMIT 1', tenant['id'], session['conversation_id'])
    if not lead or not lead['consent_contact'] or not lead['phone' if channel == 'sms' else 'email']:
        raise HTTPException(409, 'First save the caller contact and their permission using capture_lead')
    request = {'recipient': lead['phone' if channel == 'sms' else 'email'], 'channel': channel, 'content': content}
    changed = await db.pool().fetchval('UPDATE voice_sessions SET delivery_request=$2::jsonb WHERE id=$1 AND finalized_at IS NULL RETURNING id', session['id'], json.dumps(request))
    if not changed:
        raise HTTPException(409, 'This conversation has already ended')
    return {'ok': True, 'status': 'requested', 'recipient': request['recipient'], 'note': 'Requested for after this conversation is saved. It has not been sent; SMS still requires the business device Send confirmation.'}


async def recordings_for_lead(tenant_id, lead_id):
    return [dict(r) for r in await db.pool().fetch(
        "SELECT r.session_id,r.mime_type,octet_length(r.audio) AS bytes,r.created_at "
        "FROM leads l JOIN voice_recordings r ON r.conversation_id=l.conversation_id AND r.tenant_id=l.tenant_id "
        "WHERE l.tenant_id=$1 AND l.id=$2 AND r.created_at>now()-interval '30 days' ORDER BY r.created_at", tenant_id, lead_id)]


async def audio_for_owner(tenant_id, session_id):
    row = await db.pool().fetchrow(
        "SELECT audio,mime_type FROM voice_recordings WHERE tenant_id=$1 AND session_id=$2 AND created_at>now()-interval '30 days'", tenant_id, session_id)
    if not row:
        raise HTTPException(404, 'Recording not found')
    return row


async def share(tenant_id, session_id):
    await audio_for_owner(tenant_id, session_id)
    token = secrets.token_urlsafe(32)
    await db.pool().execute('INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id) VALUES($1,$2,$3)', digest(token), session_id, tenant_id)
    return token


async def shared_audio(token):
    if not 32 <= len(token) <= 100:
        raise HTTPException(404, 'Recording link expired or unavailable')
    row = await db.pool().fetchrow(
        "SELECT r.audio,r.mime_type FROM voice_recording_shares s JOIN voice_recordings r "
        "ON r.session_id=s.session_id AND r.tenant_id=s.tenant_id "
        "WHERE s.token_hash=$1 AND s.expires_at>now() AND r.created_at>now()-interval '30 days'", digest(token))
    if not row:
        raise HTTPException(404, 'Recording link expired or unavailable')
    return row


async def deliver(tenant, lead_id, *, recipient, channel, content, request_id, session_id=None):
    lead = await db.pool().fetchrow('SELECT * FROM leads WHERE tenant_id=$1 AND id=$2', tenant['id'], lead_id)
    if not lead:
        raise HTTPException(404, 'Enquiry not found')
    owner_recipient = channel == 'email' and recipient == tenant.get('notify_email')
    caller_recipient = recipient == lead['phone' if channel == 'sms' else 'email'] and bool(lead['consent_contact'])
    if not recipient or not (owner_recipient or caller_recipient):
        raise HTTPException(403, 'Use the business notification email or the consenting customer contact on this enquiry')
    if not await channel_authorization.is_authorized(tenant['id'], 'sms_send' if channel == 'sms' else 'email_send'):
        raise HTTPException(403, 'Business has not authorized this delivery channel')
    key = 'voice-copy:'+str(tenant['id'])+':'+str(request_id)
    previous = await db.pool().fetchrow('SELECT to_addr,channel,kind,lead_id FROM outbox WHERE tenant_id=$1 AND dedupe_key=$2',tenant['id'],key)
    kind='voice_recording_copy' if content == 'recording' else 'voice_text_copy'
    if previous:
        if previous['to_addr'] != recipient or previous['channel'] != channel or previous['kind'] != kind or previous['lead_id'] != lead_id:
            raise HTTPException(409, 'Delivery request identifier was already used for a different message')
        return {'status': 'already_queued'}
    if content == 'recording':
        matched = await db.pool().fetchval('SELECT 1 FROM voice_recordings WHERE session_id=$1 AND tenant_id=$2 AND conversation_id=$3', session_id, tenant['id'], lead['conversation_id'])
        if not matched:
            raise HTTPException(404, 'Recording not found for this enquiry')
        token = await share(tenant['id'], session_id)
        body = 'Your conversation with '+tenant['name']+': '+get_settings().public_base_url.rstrip('/')+'/api/v1/voice/recordings/shared/'+token+'\nThis private recording link expires in 24 hours.'
    else:
        turns = await db.pool().fetch("SELECT role,content FROM messages WHERE conversation_id=$1 AND role IN ('user','assistant') ORDER BY id LIMIT 300",lead['conversation_id'])
        if channel == 'sms':
            body = 'Your enquiry with '+tenant['name']+':\n'+'\n'.join(r['content'] for r in turns if r['role']=='user')[:700]
        else:
            body = '\n\n'.join(('Customer: ' if r['role']=='user' else 'Concierge: ')+r['content'] for r in turns)[:24000]
        if not turns:
            raise HTTPException(409, 'No saved transcript for this enquiry')
    await outbox.enqueue(tenant['id'],kind,channel,recipient,body,
        subject='Your conversation with '+tenant['name'],dedupe_key=key,lead_id=lead_id)
    return {'status': 'queued', 'note': 'Delivery is queued; it has not been confirmed sent.'}


async def purge_expired():
    await db.pool().execute("DELETE FROM voice_recordings WHERE created_at<now()-interval '30 days'")
    await db.pool().execute('DELETE FROM voice_recording_shares WHERE expires_at<now()')
    await db.pool().execute("DELETE FROM voice_sessions WHERE created_at<now()-interval '30 days'")
