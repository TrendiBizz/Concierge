"""Run from api with PYTHONPATH=../QA/verification/shims:. ; no network or real database."""
import asyncio
import json
import random
import hashlib
from unittest.mock import patch
from starlette.requests import Request
from app import asterisk_bridge as pbx, device_sms as sms
from app.telephone_recording import TelephoneRecording

async def outcome(fn):
    try:
        return {"ok": await fn()}
    except Exception as e:
        return {"err": getattr(e, 'status_code', type(e).__name__), "message": str(getattr(e, 'detail', e))}

class Pool:
    async def fetchrow(self, query, *args):
        return self.job if 'device_sms_jobs' in query else self.device

async def main():
    pool = Pool()
    pool.device = dict(id='device', tenant_id=1, from_number='+6421123456')
    tenant = dict(id=1, sms_enabled=True, sms_transport='device', sms_from='+6421123456')
    async def get_tenant(_): return current_tenant
    async def authorized(*_): return True
    auth, enqueue = [], []
    with patch.object(sms.db, 'pool', return_value=pool), patch.object(sms.tenants, 'get_by_id', get_tenant), patch.object(sms.channel_authorization, 'is_authorized', authorized):
        for header in ['', 'bearer '+'x'*40, *('Bearer '+'x'*n for n in (39,40,256,257)), 'Bearer '+'é'*40]:
            for current_tenant in [None, tenant, dict(tenant, sms_enabled=False), dict(tenant, sms_transport='carrier'), dict(tenant, sms_from='+6421999999')]:
                for receipt in [False, True]:
                    request=Request({'type':'http','path':'/receipt' if receipt else '/poll','headers':[(b'authorization',header.encode('utf-8'))]})
                    # Headers are decoded as latin-1 by ASGI.
                    actual_header=request.headers.get('Authorization','')
                    auth.append(dict(header=actual_header, tenant=current_tenant, receipt=receipt, out=await outcome(lambda: sms.device_auth(request))))
        for enabled, transport in [(False,'device'),(True,'carrier'),(True,'device')]:
            for recipient, body in [('+6421123456','hello'),('+123456','hello'),('+1234567',''),('+1234567','\u001c'),('+1234567','x'*1500),('+1234567','x'*1501),('+1٢٣٤٥٦٧','hi')]:
                for status in ['queued','claimed','sent','failed','uncertain','cancelled']:
                    for changed in [False, True]:
                        pool.job=dict(id='job',recipient=recipient,body=body+'!' if changed else body,device_id='device',status=status,receipt='verified')
                        t=dict(tenant,sms_enabled=enabled,sms_transport=transport)
                        enqueue.append(dict(enabled=enabled,transport=transport,recipient=recipient,body=body,status=status,changed=changed,out=await outcome(lambda: sms.enqueue(t,recipient,body,'key'))))
    routes=[]
    good=dict(tenant='business',number='+6421123456',port=1024)
    inputs=['{','null','[]','{}',json.dumps([good]),json.dumps([good,good])]
    for key, values in [('tenant',['','A','a'*80,'a'*81,'a\n']),('number',['+123456','+1234567','+1٢٣٤٥٦٧','+1234567\n']),('port',[1023,1024,65535,65536,'1024'])]:
        inputs += [json.dumps([dict(good,**{key:v})]) for v in values]
    inputs += [json.dumps([good,dict(good,number='+6421999999')]),json.dumps([good,dict(good,port=2000)]),json.dumps([dict(good,extra=1)])]
    for text in inputs:
        try: out={'ok':[r.__dict__ for r in pbx.routes_from_json(text)]}
        except Exception as e: out={'err':type(e).__name__, 'message':str(e)}
        routes.append(dict(text=text,out=out))
    recordings=[]
    scenarios=[[], [('append',0,'0100')], [('start',0,''),('append',0,'ff7f0080'),('append',0,'0100ffff')], [('start',1,''),('start',2,''),('append',1.001,'01000200')], [('start',0,''),('append',0,'01')], [('start',0,''),('append',600,'0100')], [('start',0,''),('append',0,'0100'),('discard',0,''),('start',2,''),('append',2,'0200')]]
    rng=random.Random(20261109)
    for _ in range(80):
        ops=[('start',1,'')]
        for _ in range(8):
            pcm=b''.join(rng.randint(-32768,32767).to_bytes(2,'little',signed=True) for _ in range(rng.randrange(0,40)))
            ops.append(('append',1+rng.randrange(-2,20)/8000,pcm.hex()))
        scenarios.append(ops)
    scenarios.append([('start',0,''),('append',599.999875,'010002000300'),('append',600,'0400')])
    for ops in scenarios:
        now=0
        r=TelephoneRecording(clock=lambda:now)
        outputs=[]
        for op,now,data in ops:
            try:
                getattr(r,op)(bytes.fromhex(data)) if op=='append' else getattr(r,op)()
                outputs.append(None)
            except Exception as e: outputs.append(str(e))
        wav=r.wav()
        recordings.append(dict(ops=ops,errors=outputs,wav_sha256=hashlib.sha256(wav).hexdigest() if wav else None))
    receipts=[]
    for job_id in ['12345678-1234-1234-1234-123456789abc','12345678123412341234123456789abc','urn:uuid:12345678-1234-1234-1234-123456789abc','{12345678-1234-1234-1234-123456789abc}','bad']:
        for status in ['sent','failed','uncertain','queued']:
            for receipt in ['', 'ok', 'é'*200, 'x'*201]:
                try:
                    model=sms.Receipt(job_id=job_id,status=status,receipt=receipt)
                    valid=not(model.status=='sent' and not model.receipt)
                except Exception: valid=False
                receipts.append(dict(job_id=job_id,status=status,receipt=receipt,valid=valid))
    incoming=[]
    for message_id in ['', 'm', 'm'*200, 'm'*201]:
        for sender in ['+6421123456','+6421999999','bad']:
            for to in ['+6421123456','+6421999999']:
                for body in ['', 'hello', 'x'*1501]:
                    try:
                        model=sms.Incoming(message_id=message_id,sender=sender,to=to,body=body)
                        valid=True
                        forbidden=model.to!='+6421123456' or model.sender=='+6421123456'
                    except Exception: valid=False; forbidden=None
                    incoming.append(dict(message_id=message_id,sender=sender,to=to,body=body,valid=valid,forbidden=forbidden))
    hashes=[dict(token=t,out=sms.token_hash(t)) for t in ['', 'x'*40, 'é日本', 'x'*256]]
    # Capture the exact operational argument passed by the real inbound handler.
    keywords=[]
    async def reply(*args,**kwargs): return 'reply'
    class DuplicatePool(Pool):
        async def fetchval(self,*args): return 'inserted'
        async def execute(self,*args): pass
    async def capture(*args,**kwargs):
        keywords.append(dict(body=current_body,out=kwargs['operational']))
        raise sms.AwaitingReceipt('job')
    from app import main as http_main
    with patch.object(sms.db,'pool',return_value=DuplicatePool()), patch.object(sms.tenants,'get_by_id',get_tenant), patch.object(sms.channel_authorization,'is_authorized',authorized), patch.object(http_main,'_sms_reply',reply), patch.object(sms,'enqueue',capture):
        for current_body in ['STOP','stop',' STOPALL ', '\u001cHELP\u001c','START','UNSTOP','UNSUBSCRIBE','CANCEL','END','QUIT','hello','STOP now','ſtop']:
            await sms.inbound(sms.Incoming(message_id='id',sender='+6421999999',to='+6421123456',body=current_body),pool.device)
    packets=[]
    class Writer:
        def write(self,b): self.data=b
        async def drain(self): pass
    for kind in [0,3,16,255]:
        for length in [0,1,8192,8193,65535]:
            body=bytes([42])*length
            writer=Writer()
            await pbx.send_packet(writer,kind,body)
            reader=asyncio.StreamReader()
            reader.feed_data(writer.data)
            reader.feed_eof()
            result=await outcome(lambda:pbx.packet(reader))
            packets.append(dict(kind=kind,length=length,encoded=writer.data.hex(),accepted='ok' in result))
    print(json.dumps(dict(auth=auth,enqueue=enqueue,routes=routes,recordings=recordings,receipts=receipts,packets=packets,incoming=incoming,hashes=hashes,keywords=keywords),ensure_ascii=False,indent=1))

asyncio.run(main())
