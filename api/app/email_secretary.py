"""Opt-in email receptionist. Verified ingress only; deliveries use the outbox."""
import asyncio
import hashlib
from . import channel_authorization, chat, db, flood_guard, outbox, tenants


async def process_once():
    rows = await db.pool().fetch(
        "UPDATE email_secretary_jobs SET status='processing',attempts=attempts+1,claimed_at=now() WHERE id IN ("
        "SELECT j.id FROM email_secretary_jobs j JOIN tenants t ON t.id=j.tenant_id "
        "WHERE t.email_auto_reply AND (j.status='pending' OR (j.status='processing' AND j.claimed_at<now()-interval '10 minutes')) "
        "AND j.attempts<3 ORDER BY j.id LIMIT 10 FOR UPDATE OF j SKIP LOCKED) RETURNING *")
    for job in rows:
        try:
            tenant = await tenants.get_by_id(job['tenant_id'])
            if not tenant.get('email_auto_reply') or not await channel_authorization.is_authorized(tenant['id'], 'email_read') or not await channel_authorization.is_authorized(tenant['id'], 'email_send'):
                await db.pool().execute("UPDATE email_secretary_jobs SET status='held',error='Authorize email reading and sending before retry' WHERE id=$1", job['id'])
                continue
            draft_status = await db.pool().fetchval('SELECT status FROM email_drafts WHERE tenant_id=$1 AND source_id=$2', tenant['id'], job['source_key'])
            if draft_status != 'draft':
                await db.pool().execute("UPDATE email_secretary_jobs SET status='held',error='Already reviewed by owner' WHERE id=$1", job['id'])
                continue
            if flood_guard.automated_message(job['sender'], job['subject']):
                # Never auto-reply to a robot (noreply, mailer-daemon, out-of-office): two
                # auto-responders will answer each other forever.
                await db.pool().execute("UPDATE email_secretary_jobs SET status='held',error='Automated sender: no automatic reply' WHERE id=$1", job['id'])
                continue
            session = 'email' + hashlib.sha256(job['sender'].lower().encode()).hexdigest()[:50]
            result = await chat.run_turn(tenant, session, 'email', 'Subject: ' + job['subject'] + '\n\n' + job['body'], sender_email=job['sender'])

            # Human takeover: the owner has taken this customer over, so no automatic reply is sent.
            # The job is marked 'held' rather than 'failed' -- it is not an error, and the owner may
            # resume it. Without this check a suppressed turn queued an EMPTY-BODY email to the
            # customer, because a suppressed turn correctly returns an empty reply.
            if result.get('suppressed') or not (result.get('reply') or '').strip():
                await db.pool().execute(
                    "UPDATE email_secretary_jobs SET status='held',error=$2 WHERE id=$1",
                    job['id'],
                    'Human takeover: the owner is handling this customer' if result.get('suppressed')
                    else 'No reply produced; not queued')
                continue

            async with db.pool().acquire() as conn:
                async with conn.transaction():
                    draft = await conn.fetchrow('SELECT * FROM email_drafts WHERE tenant_id=$1 AND source_id=$2 FOR UPDATE', tenant['id'], job['source_key'])
                    if not draft or draft['status'] != 'draft':
                        await conn.execute("UPDATE email_secretary_jobs SET status='held',error='Already reviewed by owner' WHERE id=$1", job['id'])
                        continue
                    await conn.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key) VALUES($1,'email_secretary_reply','email',$2,$3,$4,$5) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING", tenant['id'], job['sender'], 'Re: ' + job['subject'], result['reply'], f"email-secretary:{tenant['id']}:{job['source_key']}")
                    await conn.execute("UPDATE email_drafts SET status='discarded',reply_body=$3,updated_at=now() WHERE tenant_id=$1 AND id=$2", tenant['id'], draft['id'], result['reply'])
                    await conn.execute("UPDATE email_secretary_jobs SET status='queued',error='' WHERE id=$1", job['id'])
        except Exception:
            await db.pool().execute("UPDATE email_secretary_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END,error='Email processing failed; reply not confirmed' WHERE id=$1", job['id'])


async def run_forever(stop):
    while not stop.is_set():
        try:
            await process_once()
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Email secretary processing will retry')
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass

# Only metadata is exposed; message content remains in tenant-private CRM.
from fastapi import APIRouter, Depends, HTTPException
from . import owner_auth
router = APIRouter(prefix='/owner/email-secretary', tags=['email'])


@router.get('/jobs')
async def jobs(user=Depends(owner_auth.current_user)):
    rows = await db.pool().fetch('SELECT id,sender,subject,status,attempts,error FROM email_secretary_jobs WHERE tenant_id=$1 ORDER BY id DESC LIMIT 100', user['tenant_id'])
    return [dict(row) for row in rows]


@router.post('/jobs/{job_id}/retry')
async def retry(job_id: int, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, 'owner')
    tenant = await tenants.get_by_id(user['tenant_id'])
    if not tenant.get('email_auto_reply') or not await channel_authorization.is_authorized(tenant['id'], 'email_read') or not await channel_authorization.is_authorized(tenant['id'], 'email_send'):
        raise HTTPException(409, 'Enable automatic replies and authorize email reading and sending first')
    row = await db.pool().fetchrow("UPDATE email_secretary_jobs j SET status='pending',attempts=0,error='' WHERE j.id=$1 AND j.tenant_id=$2 AND j.status IN ('held','failed') AND EXISTS(SELECT 1 FROM email_drafts d WHERE d.tenant_id=j.tenant_id AND d.source_id=j.source_key AND d.status='draft') RETURNING j.id,j.status", job_id, tenant['id'])
    if not row:
        raise HTTPException(409, 'Work unavailable, already queued or handled by owner')
    return dict(row)
