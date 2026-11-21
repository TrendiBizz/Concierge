"""Disposable DB + real bridge protocol test. No send worker, no real messages.
DATABASE_URL must point to an empty, disposable PostgreSQL database.
"""
import asyncio
import ipaddress
import json
import os
import uuid

import websockets
from app import asterisk_bridge as b, db
from app.config import get_settings

async def main():
    cfg=get_settings()
    assert 'fixture-only' in cfg.database_url, 'Disposable fixture database required'
    cfg.phone_receptionist_enabled=True
    cfg.xai_api_key='fixture-only'
    await db.init()
    pool=db.pool()
    assert not await pool.fetchval('SELECT count(*) FROM tenants'), 'Empty fixture DB required'
    created=[]
    transcripts={}
    async def fake_grok(ws):
        update=json.loads(await ws.recv())
        instructions=update['session']['instructions']
        business=next(name for name in ('Alpha Workshop','Beta Florist') if name in instructions)
        assert update['session']['audio']['input']['format']['rate']==8000
        await ws.send(json.dumps({'type':'session.updated'}))
        emitted=False
        async for raw in ws:
            event=json.loads(raw)
            if event['type']=='input_audio_buffer.append' and not emitted:
                emitted=True
                await ws.send(json.dumps({'type':'conversation.item.input_audio_transcription.completed',
                    'item_id':'same-call-local-id','transcript':f'Message specifically for {business}'}))
                transcripts[business]=True
    ws_server=await websockets.serve(fake_grok,'127.0.0.1',0)
    cfg.xai_realtime_url=f'ws://127.0.0.1:{ws_server.sockets[0].getsockname()[1]}'
    servers=[]
    writers=[]
    try:
        for i,(slug,name) in enumerate((('alpha','Alpha Workshop'),('beta','Beta Florist'))):
            tenant=dict(await pool.fetchrow("INSERT INTO tenants(slug,name,public_key,phone_enabled) VALUES($1,$2,$3,true) RETURNING *",slug,name,'fixture-'+slug))
            created.append(tenant)
            number=f'+649555010{i}'
            await pool.execute('INSERT INTO phone_numbers(e164,tenant_id,enabled) VALUES($1,$2,true)',number,tenant['id'])
            await pool.execute("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,'telephone',true,$2)",tenant['id'],uuid.uuid4())
            await pool.execute("INSERT INTO managed_phone_setups(tenant_id,designated_number,connection,answer_mode,owner_number) VALUES($1,$2,'mobile_forwarding','unanswered',$3)",tenant['id'],number,f'+6421555010{i}')
            route=b.Route(slug,number,9101+i)
            server=await asyncio.start_server(lambda r,w,route=route:b.handle(r,w,route,[ipaddress.ip_network('127.0.0.1/32')]),'127.0.0.1',0)
            servers.append(server)
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            writers.append(writer)
            ident=uuid.uuid4()
            await b.send_packet(writer,1,ident.bytes)
            await b.send_packet(writer,0x10,b'\0'*320)
        async with asyncio.timeout(5):
            while len(transcripts)<2:
                await asyncio.sleep(.02)
        for writer in writers:
            await b.send_packet(writer,0)
        async with asyncio.timeout(5):
            while await pool.fetchval('SELECT count(*) FROM phone_calls WHERE ended_at IS NULL'):
                await asyncio.sleep(.02)
        rows=await pool.fetch("SELECT t.slug,l.message,o.to_addr,o.body FROM tenants t JOIN leads l ON l.tenant_id=t.id JOIN outbox o ON o.tenant_id=t.id WHERE o.channel='sms' ORDER BY t.slug")
        assert len(rows)==2, [dict(r) for r in rows]
        for i,row in enumerate(rows):
            name=('Alpha Workshop','Beta Florist')[i]
            other=('Beta Florist','Alpha Workshop')[i]
            assert name in row['message'] and other not in row['message']
            assert name in row['body'] and other not in row['body']
            assert row['to_addr']==f'+6421555010{i}'
        first=await pool.fetchrow('SELECT * FROM phone_calls ORDER BY started_at LIMIT 1')
        try:
            await b.register(b.Route('beta','+6495550101',9102),first['call_sid'])
            raise AssertionError('Cross-business UUID replay accepted')
        except Exception as error:
            assert type(error).__name__=='UniqueViolationError',type(error).__name__
        print('PASS: two concurrent business routes → Grok protocol → separate CRM transcripts → correct owner SMS queues; cross-business replay rejected; real sends=0')
    finally:
        for writer in writers:
            writer.close()
            await writer.wait_closed()
        for server in servers:
            server.close()
            await server.wait_closed()
        ws_server.close()
        await ws_server.wait_closed()
        await db.close()

asyncio.run(main())
