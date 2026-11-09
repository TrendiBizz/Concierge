"""Tenant-specific mobile forwarding destinations and real-call verification."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from . import channel_authorization, db, owner_auth, tenants
from .security import require_admin

router=APIRouter()


class MobileConnection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    destination: str = Field(pattern=r'^\+[1-9]\d{6,14}$')
    carrier: Literal['spark_nz','other'] = 'other'


def forwarding_steps(destination, carrier, mode):
    if carrier != 'spark_nz':
        return [{'label':'Set call forwarding with your mobile carrier to '+destination,
                 'destination':destination}]
    # Spark's published mobile diversion codes. Owner explicitly dials; never
    # invoke automatically or replace the existing voicemail configuration.
    modes=[('Forward all calls','21')] if mode=='all_calls' else [
        ('Forward unanswered calls','61'),('Forward busy calls','67')]
    return [{'label':label,'dial':f'*{code}*{destination}*11#',
             'check':f'*#{code}*11#'} for label,code in modes]


@router.put('/admin/tenants/{slug}/mobile-connection',dependencies=[Depends(require_admin)])
async def bind_mobile_connection(slug: str, body: MobileConnection):
    tenant=await tenants.get_by_slug(slug)
    if not tenant:raise HTTPException(404,'Business not found')
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            setup=await conn.fetchrow('SELECT * FROM managed_phone_setups WHERE tenant_id=$1 FOR UPDATE',tenant['id'])
            if not setup or setup['connection']!='mobile_forwarding':
                raise HTTPException(409,'Save the business mobile setup first')
            if body.destination==setup['designated_number']:
                raise HTTPException(409,'Forwarding destination must differ from the public mobile number')
            if not await conn.fetchval('SELECT 1 FROM phone_numbers WHERE tenant_id=$1 AND e164=$2 AND enabled',tenant['id'],body.destination):
                raise HTTPException(409,'Connect and enable this business’s actual ingress destination first')
            await conn.execute('INSERT INTO mobile_forwarding_connections(tenant_id,destination,carrier) VALUES($1,$2,$3) ON CONFLICT(tenant_id) DO UPDATE SET destination=EXCLUDED.destination,carrier=EXCLUDED.carrier,created_at=now()',tenant['id'],body.destination,body.carrier)
            await conn.execute("UPDATE managed_phone_setups SET status='test_required',updated_at=now() WHERE tenant_id=$1",tenant['id'])
    return {'status':'ready_to_forward','destination':body.destination,'carrier':body.carrier}


@router.get('/owner/mobile-connection')
async def mobile_connection(user: dict=Depends(owner_auth.current_user)):
    row=await db.pool().fetchrow('SELECT m.destination,m.carrier,m.created_at,s.answer_mode,s.designated_number,s.connection FROM mobile_forwarding_connections m JOIN managed_phone_setups s ON s.tenant_id=m.tenant_id JOIN phone_numbers p ON p.tenant_id=m.tenant_id AND p.e164=m.destination AND p.enabled WHERE m.tenant_id=$1',user['tenant_id'])
    if not row or row['connection']!='mobile_forwarding':
        return {'status':'destination_needed','steps':[]}
    if row['destination']==row['designated_number']:
        return {'status':'destination_needed','steps':[]}
    if not await channel_authorization.is_authorized(user['tenant_id'],'telephone'):
        return {'status':'authorization_needed','steps':[]}
    call=await db.pool().fetchrow("SELECT p.call_sid,p.status, EXISTS(SELECT 1 FROM outbox o WHERE o.tenant_id=p.tenant_id AND o.dedupe_key=p.call_sid||':owner') AS owner_message_queued FROM phone_calls p WHERE p.tenant_id=$1 AND p.to_number=$2 AND p.started_at>=$3 ORDER BY p.started_at DESC LIMIT 1",user['tenant_id'],row['destination'],row['created_at'])
    return {'status':'call_received' if call else 'ready_to_forward','destination':row['destination'],
            'carrier':row['carrier'],'steps':forwarding_steps(row['destination'],row['carrier'],row['answer_mode']),
            'last_call':dict(call) if call else None}
