"""Real PostgreSQL/API isolation checks. Disposable test database only; no sends."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from unittest.mock import AsyncMock, patch

os.environ.update({
    "DATABASE_URL":"postgresql://postgres:test@trendi-phone-test-db:5432/postgres",
    "ADMIN_TOKEN":"disposable-phone-test-admin","OUTBOX_ENABLED":"false",
    "TWENTY_BRIDGE_URL":"","XAI_API_KEY":"not-a-real-key",
    "SMS_QUIET_START_HOUR":"0","SMS_QUIET_END_HOUR":"24",
})
from fastapi.testclient import TestClient
from app import db, device_sms, outbox, phone_sip, tenants, owner_auth
from app.main import app

checks=0
def check(label,value):
    global checks
    assert value,label
    checks+=1;print("PASS",label,flush=True)

with TestClient(app) as client:
    run=client.portal.call;p=db.pool()
    async def seed():
        result=[]
        for slug,number,token in [('a','+64215550101','a'*48),('b','+64215550102','b'*48)]:
            tenant=await p.fetchrow("INSERT INTO tenants(slug,name,public_key,sms_enabled,sms_transport,sms_from,phone_enabled,timezone) VALUES($1,$1,$1,true,'device',$2,true,'UTC') RETURNING *",slug,number)
            uid=await p.fetchval("INSERT INTO tenant_users(tenant_id,email,role,password_hash) VALUES($1,$2,'owner','test') RETURNING id",tenant['id'],slug+'@example.invalid')
            for channel in ['sms_read','sms_send','telephone']:
                await p.execute("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,$2,true,$3)",tenant['id'],channel,uid)
            device=await p.fetchrow("INSERT INTO sms_devices(tenant_id,token_hash,from_number,enabled) VALUES($1,$2,$3,true) RETURNING *",tenant['id'],device_sms.token_hash(token),number)
            result.append((dict(tenant),dict(device),{'Authorization':'Bearer '+token}))
        return result
    (a,ad,ah),(b,bd,bh)=run(seed)
    check('missing device credentials rejected',client.post('/api/v1/device-sms/poll',json={}).status_code==401)
    check('unknown device credentials rejected',client.post('/api/v1/device-sms/poll',headers={'Authorization':'Bearer '+'z'*48},json={}).status_code==401)
    check('paired phone heartbeat, no historical jobs',client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()=={'job':None})

    async def queued(tenant,key,outbox_id=None):
        try:
            await device_sms.enqueue(tenant,'+64215550999','Exact approved text',key,outbox_id)
        except device_sms.AwaitingReceipt as pending:
            return str(pending)
    job=run(queued,a,'approved:one')
    check('new send waits for real receipt',bool(uuid.UUID(job)))
    check('repeating queue operation is idempotent',run(queued,a,'approved:one')==job)
    check('other tenant cannot claim text',client.post('/api/v1/device-sms/poll',headers=bh,json={}).json()=={'job':None})
    claimed=client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()['job']
    check('correct phone gets exact content and sender',claimed['id']==job and claimed['body']=='Exact approved text' and claimed['from_number']==a['sms_from'])
    check('claimed job is never handed out twice',client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()=={'job':None})
    receipt={'job_id':job,'status':'sent','receipt':'Messages-guid-verified'}
    check('other phone cannot forge receipt',client.post('/api/v1/device-sms/receipt',headers=bh,json=receipt).status_code==409)
    check('sent requires verified receipt',client.post('/api/v1/device-sms/receipt',headers=ah,json={**receipt,'receipt':''}).status_code==422)
    check('correct verified receipt accepted',client.post('/api/v1/device-sms/receipt',headers=ah,json=receipt).status_code==200)
    check('receipt replay is idempotent',client.post('/api/v1/device-sms/receipt',headers=ah,json=receipt).status_code==200)
    check('confirmed job returns same receipt without another send',run(device_sms.enqueue,a,'+64215550999','Exact approved text','approved:one')=='Messages-guid-verified')

    async def outbox_row(old=False):
        return dict(await p.fetchrow("INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,created_at) VALUES($1,'confirmation','sms','+64215550998','Approved confirmation','sending',now()-$2*interval '1 day') RETURNING *",a['id'],1 if old else 0))
    row=run(outbox_row)
    run(outbox._deliver,row)
    check('outbox queued is not falsely sent',run(lambda:p.fetchval('SELECT status FROM outbox WHERE id=$1',row['id']))=='awaiting_receipt')
    device_sms.get_settings().sms_quiet_start_hour=23
    device_sms.get_settings().sms_quiet_end_hour=23
    check('quiet hours rechecked at actual phone dispatch',client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()=={'job':None})
    device_sms.get_settings().sms_quiet_start_hour=0
    device_sms.get_settings().sms_quiet_end_hour=24
    delivery=client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()['job']
    client.post('/api/v1/device-sms/receipt',headers=ah,json={'job_id':delivery['id'],'status':'sent','receipt':'receipt-two'})
    check('outbox only becomes sent after receipt',run(lambda:p.fetchval('SELECT status FROM outbox WHERE id=$1',row['id']))=='sent')
    old=run(outbox_row,True);run(outbox._deliver,old)
    check('activation cannot replay historical queued SMS',run(lambda:p.fetchval('SELECT status FROM outbox WHERE id=$1',old['id']))=='held')

    lost=run(queued,a,'approved:lost')
    client.post('/api/v1/device-sms/poll',headers=ah,json={})
    run(lambda:p.execute("UPDATE device_sms_jobs SET claimed_at=now()-interval '6 minutes' WHERE id=$1",uuid.UUID(lost)))
    check('lost receipt does not cause second send',client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()=={'job':None})
    check('lost receipt flagged uncertain',run(lambda:p.fetchval('SELECT status FROM device_sms_jobs WHERE id=$1',uuid.UUID(lost)))=='uncertain')

    run(queued,a,'approved:optout')
    run(outbox.opt_out,a['id'],'+64215550999')
    check('opt-out rechecked at actual device claim',client.post('/api/v1/device-sms/poll',headers=ah,json={}).json()=={'job':None})
    run(lambda:p.execute('UPDATE tenants SET sms_enabled=false WHERE id=$1',a['id']))
    check('revoked connection blocks phone poll',client.post('/api/v1/device-sms/poll',headers=ah,json={}).status_code==403)
    run(lambda:p.execute('UPDATE tenants SET sms_enabled=true WHERE id=$1',a['id']))

    message={'message_id':'incoming-unique','sender':'+64215550777','to':a['sms_from'],'body':'Business question'}
    with patch('app.main._sms_reply',new=AsyncMock(return_value='Grok reply queued for native approval')) as grok:
        check('another SIM cannot inject into business line',client.post('/api/v1/device-sms/inbound',headers=bh,json=message).status_code==403)
        check('own messages cannot create reply loops',client.post('/api/v1/device-sms/inbound',headers=ah,json={**message,'sender':a['sms_from']}).status_code==403)
        check('new business SMS reaches shared Grok path',client.post('/api/v1/device-sms/inbound',headers=ah,json=message).status_code==200)
        check('replayed inbound does not generate second reply',client.post('/api/v1/device-sms/inbound',headers=ah,json=message).json().get('duplicate') and grok.await_count==1)
        check('Grok sees correct tenant and sender',grok.call_args.args[0]['id']==a['id'] and grok.call_args.args[1]==message['sender'])

    app.dependency_overrides[owner_auth.current_user]=lambda:{'tenant_id':b['id'],'slug':'b','role':'viewer'}
    check('viewer cannot queue phone test',client.post('/owner/sms-phone/test',json={'acknowledgement':True,'request_id':str(uuid.uuid4())}).status_code==403)
    app.dependency_overrides[owner_auth.current_user]=lambda:{'tenant_id':b['id'],'slug':'b','role':'owner'}
    check('test cannot override recipient',client.post('/owner/sms-phone/test',json={'acknowledgement':True,'request_id':str(uuid.uuid4()),'recipient':'+64215550999'}).status_code==422)
    check('owner can queue fixed test only to own number',client.post('/owner/sms-phone/test',json={'acknowledgement':True,'request_id':str(uuid.uuid4())}).status_code==202)
    own=client.get('/owner/sms-phone').json()
    check('owner sees only own connection and messages',own['number']==b['sms_from'] and len(own['messages'])==1 and own['messages'][0]['recipient']==b['sms_from'])
    check('device credential never returned to owner status',bd['token_hash'] not in json.dumps(own) and 'token' not in json.dumps(own))
    app.dependency_overrides.clear()

    connection=str(uuid.uuid4());call_id=str(uuid.uuid4());key=base64.b64encode(b'k'*32).decode();secret='whsec_'+key
    phone_sip.get_settings().xai_sip_connections=json.dumps({connection:{'enabled':True,'tenant':'a','number':a['sms_from'],'signing_secret':secret}})
    hook='/api/v1/phone/xai/'+connection
    def signed_event(to=None,call=None):
        raw=json.dumps({'type':'realtime.call.incoming','data':{'call_id':call or call_id,'sip_headers':[{'name':'To','value':to or a['sms_from']},{'name':'From','value':'+64215550666'}]}}).encode()
        stamp=str(int(time.time()));ident='evt_'+str(uuid.uuid4())
        sig=base64.b64encode(hmac.new(b'k'*32,(ident+'.'+stamp+'.').encode()+raw,hashlib.sha256).digest()).decode()
        return raw,{'webhook-id':ident,'webhook-timestamp':stamp,'webhook-signature':'v1,'+sig,'Content-Type':'application/json'}
    raw,headers=signed_event()
    check('unsigned SIP cannot reach Grok or call registry',client.post(hook,content=raw,headers={}).status_code==403)
    check('inactive phone number blocks signed SIP',client.post(hook,content=raw,headers=headers).status_code==403)
    run(lambda:p.execute('INSERT INTO phone_numbers(e164,tenant_id,enabled) VALUES($1,$2,true)',a['sms_from'],a['id']))
    with patch.object(phone_sip.events,'spawn',side_effect=lambda coroutine:coroutine.close()):
        check('verified customer-owned SIP is accepted',client.post(hook,content=raw,headers=headers).status_code==200)
        check('provider webhook replay does not answer twice',client.post(hook,content=raw,headers=headers).json().get('duplicate'))
        bad,bad_headers=signed_event(to=b['sms_from'],call=str(uuid.uuid4()))
        check('SIP destination cannot cross workspace',client.post(hook,content=bad,headers=bad_headers).status_code==403)
        run(lambda:p.execute('UPDATE tenants SET phone_daily_limit=0 WHERE id=$1',a['id']))
        quota,quota_headers=signed_event(call=str(uuid.uuid4()))
        check('SIP daily limit enforced before answering',client.post(hook,content=quota,headers=quota_headers).status_code==429)
    check('one unique call row persisted',run(lambda:p.fetchval("SELECT count(*) FROM phone_calls WHERE tenant_id=$1",a['id']))==1)

print('Device SMS and carrier-independent SIP:',checks,'checks passed; no external calls or texts sent.')
