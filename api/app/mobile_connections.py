"""Tenant-specific mobile forwarding destinations and real-call verification."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from . import call_forwarding, channel_authorization, db, owner_auth, tenants
from .security import require_admin

router=APIRouter()


class MobileConnection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    destination: str = Field(pattern=r'^\+[1-9]\d{6,14}$')
    carrier: str = Field(default='other',max_length=40)


class MobilePreferences(BaseModel):
    """What an owner may choose. The destination number is deliberately not here: only an admin binds it."""
    model_config=ConfigDict(extra='forbid')
    country: str | None = Field(default=None,max_length=2)
    carrier: str | None = Field(default=None,max_length=40)
    answer_mode: Literal['all_calls','unanswered'] | None = None


def forwarding_steps(destination, carrier, mode, country='ZZ'):
    return call_forwarding.steps(destination,carrier,mode,country)


def country_warning(destination, tenant):
    """A warning (never a block) when the number is not in the business's own calling country."""
    dial=call_forwarding.tenant_dial_code(tenant)
    if dial and not destination.lstrip('+').startswith(dial):
        return ('This number is not in the business\'s own country (+'+dial+'). Owners forward calls to it '
                'from their mobile, so it should normally be bought in their country.')


def _selected_country(prefs, connection_carrier, tenant):
    if prefs and prefs['country']:
        return call_forwarding.normalize_country(prefs['country'])
    carrier=call_forwarding.data()['carriers'].get(connection_carrier or 'other',{})
    if carrier.get('country'):
        return carrier['country']
    return call_forwarding.country_for_dial(call_forwarding.tenant_dial_code(tenant)) or 'ZZ'


@router.put('/admin/tenants/{slug}/mobile-connection',dependencies=[Depends(require_admin)])
async def bind_mobile_connection(slug: str, body: MobileConnection):
    tenant=await tenants.get_by_slug(slug)
    if not tenant:raise HTTPException(404,'Business not found')
    carrier=call_forwarding.normalize_carrier(body.carrier)
    destination_country=call_forwarding.country_for_e164(body.destination)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            setup=await conn.fetchrow('SELECT * FROM managed_phone_setups WHERE tenant_id=$1 FOR UPDATE',tenant['id'])
            if not setup or setup['connection']!='mobile_forwarding':
                raise HTTPException(409,'Save the business mobile setup first')
            if body.destination==setup['designated_number']:
                raise HTTPException(409,'Forwarding destination must differ from the public mobile number')
            if not await conn.fetchval('SELECT 1 FROM phone_numbers WHERE tenant_id=$1 AND e164=$2 AND enabled',tenant['id'],body.destination):
                raise HTTPException(409,'Connect and enable this business’s actual ingress destination first')
            await conn.execute('INSERT INTO mobile_forwarding_connections(tenant_id,destination,carrier,destination_country) VALUES($1,$2,$3,$4) ON CONFLICT(tenant_id) DO UPDATE SET destination=EXCLUDED.destination,carrier=EXCLUDED.carrier,destination_country=EXCLUDED.destination_country,created_at=now()',tenant['id'],body.destination,carrier,destination_country)
            await conn.execute("UPDATE managed_phone_setups SET status='test_required',updated_at=now() WHERE tenant_id=$1",tenant['id'])
    result={'status':'ready_to_forward','destination':body.destination,'carrier':carrier,'destination_country':destination_country}
    warning=country_warning(body.destination,tenant)
    if warning:result['warning']=warning
    return result


@router.put('/owner/mobile-connection')
async def save_mobile_preferences(body: MobilePreferences, user: dict=Depends(owner_auth.current_user)):
    owner_auth.require_role(user,'owner')
    country=call_forwarding.normalize_country(body.country) if body.country else None
    carrier=call_forwarding.normalize_carrier(body.carrier,country if country and country!='ZZ' else None) if body.carrier else None
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute('INSERT INTO call_forwarding_preferences(tenant_id,country,carrier,answer_mode) VALUES($1,$2,$3,$4) ON CONFLICT(tenant_id) DO UPDATE SET country=COALESCE($2,call_forwarding_preferences.country),carrier=COALESCE($3,call_forwarding_preferences.carrier),answer_mode=COALESCE($4,call_forwarding_preferences.answer_mode),updated_at=now()',user['tenant_id'],country,carrier,body.answer_mode)
            if country and not carrier:
                # A carrier saved for the previous country no longer applies.
                saved=await conn.fetchval('SELECT carrier FROM call_forwarding_preferences WHERE tenant_id=$1',user['tenant_id'])
                if saved and call_forwarding.normalize_carrier(saved,country if country!='ZZ' else None)=='other' and saved!='other':
                    await conn.execute('UPDATE call_forwarding_preferences SET carrier=NULL WHERE tenant_id=$1',user['tenant_id'])
            if body.answer_mode:
                await conn.execute('UPDATE managed_phone_setups SET answer_mode=$2,updated_at=now() WHERE tenant_id=$1',user['tenant_id'],body.answer_mode)
    return await mobile_connection(user)


@router.get('/owner/mobile-connection')
async def mobile_connection(user: dict=Depends(owner_auth.current_user)):
    pool=db.pool()
    tenant=await pool.fetchrow('SELECT t.default_country_code,t.timezone,t.notify_phone,f.country AS pref_country,f.carrier AS pref_carrier,f.answer_mode AS pref_answer_mode FROM tenants t LEFT JOIN call_forwarding_preferences f ON f.tenant_id=t.id WHERE t.id=$1',user['tenant_id'])
    tenant=dict(tenant) if tenant else {}
    row=await pool.fetchrow('SELECT m.destination,m.carrier,m.created_at,m.destination_country,s.answer_mode,s.designated_number,s.connection FROM mobile_forwarding_connections m JOIN managed_phone_setups s ON s.tenant_id=m.tenant_id JOIN phone_numbers p ON p.tenant_id=m.tenant_id AND p.e164=m.destination AND p.enabled WHERE m.tenant_id=$1',user['tenant_id'])
    row=dict(row) if row else None
    usable=bool(row) and row['connection']=='mobile_forwarding' and row['destination']!=row['designated_number']
    prefs={'country':tenant.get('pref_country'),'carrier':tenant.get('pref_carrier')}
    country=_selected_country(prefs,row['carrier'] if row else None,tenant)
    carrier=call_forwarding.normalize_carrier(prefs['carrier'] or (row['carrier'] if row else None),country if country!='ZZ' else None)
    mode=(row['answer_mode'] if row else None) or tenant.get('pref_answer_mode') or 'unanswered'
    lists=call_forwarding.picker_lists()['countries']
    base={'country':country,'carrier':carrier,'answer_mode':mode,'notify_phone':tenant.get('notify_phone'),
          'tenant_country_code':call_forwarding.tenant_dial_code(tenant),
          'countries':lists,'carriers':next(c['carriers'] for c in lists if c['code']==country),
          'device_hints':call_forwarding.device_hints(),
          'steps':{'set':[],'check':[],'cancel':[],'cancel_all':call_forwarding.data()['gsm']['cancel_all']},
          'last_call':None,'destination':None}
    if not usable:
        return {**base,'status':'destination_needed'}
    if not await channel_authorization.is_authorized(user['tenant_id'],'telephone'):
        return {**base,'status':'authorization_needed'}
    dest=row['destination']
    call=await pool.fetchrow("SELECT p.call_sid,p.status, EXISTS(SELECT 1 FROM outbox o WHERE o.tenant_id=p.tenant_id AND o.dedupe_key=p.call_sid||':owner') AS owner_message_queued FROM phone_calls p WHERE p.tenant_id=$1 AND p.to_number=$2 AND p.started_at>=$3 ORDER BY p.started_at DESC LIMIT 1",user['tenant_id'],dest,row['created_at'])
    dest_country=row['destination_country'] or call_forwarding.country_for_e164(dest)
    same=call_forwarding.matches_destination
    return {**base,'status':'call_received' if call else 'ready_to_forward','destination':dest,
            'destination_display':call_forwarding.dial_number(dest,country),
            'destination_country':dest_country,
            'country_mismatch':call_forwarding.is_cross_country(dest,country),
            'destination_is_notify_phone':same(tenant.get('notify_phone'),dest,country),
            'destination_is_public_mobile':same(row['designated_number'],dest,country),
            'steps':forwarding_steps(dest,carrier,mode,country),
            'last_call':dict(call) if call else None}
