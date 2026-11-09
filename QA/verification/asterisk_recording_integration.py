"""Disposable DB + real bridge protocol test. No send worker, no real messages.
DATABASE_URL must point to an empty, disposable PostgreSQL database.
"""
import base64
import io
import wave
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
    cfg.voice_recording_enabled=True
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
                async def invoke(name, args, ident):
                    await ws.send(json.dumps({'type':'response.function_call_arguments.done','name':name,'call_id':ident,'arguments':json.dumps(args)}))
                    await ws.send(json.dumps({'type':'response.done'}))
                    while True:
                        reply=json.loads(await ws.recv())
                        if reply['type']=='conversation.item.create':
                            return json.loads(reply['item']['output'])
                denied=await invoke('set_call_recording',{'enabled':True,'confirmed':False},'not-confirmed')
                assert denied['ok'] is False
                if business=='Alpha Workshop':
                    accepted=await invoke('set_call_recording',{'enabled':True,'confirmed':True},'confirmed')
                    assert accepted['recording'] is True
                    await ws.send(json.dumps({'type':'response.output_audio.delta','delta':base64.b64encode(b'\x01\x00'*1600).decode()}))
                    await asyncio.sleep(.3)
                    captured=await invoke('capture_lead',{'name':'Fixture Caller','phone':'+64215550222','message':'Please call me back about Alpha','consent_to_contact':True},'capture')
                    assert captured.get('ok',True), captured
                    requested=await invoke('request_conversation_copy',{'channel':'sms','content':'recording','confirmed':True},'copy')
                    assert requested['status']=='requested', requested
                else:
                    started=await invoke('set_call_recording',{'enabled':True,'confirmed':True},'temporary')
                    assert started['recording'] is True
                    await ws.send(json.dumps({'type':'response.output_audio.delta','delta':base64.b64encode(b'\x02\x00'*1600).decode()}))
                    await asyncio.sleep(.3)
                    stopped=await invoke('set_call_recording',{'enabled':False,'confirmed':True},'withdrawn')
                    assert stopped['recording'] is False
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
            for channel in ('call_recording','sms_send'):
                await pool.execute("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,$2,true,$3)",tenant['id'],channel,uuid.uuid4())
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
        rows=await pool.fetch("SELECT t.slug,l.message,o.to_addr,o.body FROM tenants t JOIN leads l ON l.tenant_id=t.id JOIN outbox o ON o.tenant_id=t.id WHERE o.channel='sms' AND o.kind='owner_alert' ORDER BY t.slug")
        assert len(rows)==2, [dict(r) for r in rows]
        for i,row in enumerate(rows):
            name=('Alpha Workshop','Beta Florist')[i]
            other=('Beta Florist','Alpha Workshop')[i]
            assert name in row['message'] and other not in row['message']
            assert name in row['body'] and other not in row['body']
            assert row['to_addr']==f'+6421555010{i}'
        async with asyncio.timeout(5):
            while not await pool.fetchval("SELECT count(*) FROM outbox WHERE kind='voice_recording_copy'"):
                await asyncio.sleep(.02)
        recordings=await pool.fetch('SELECT r.*,t.slug FROM voice_recordings r JOIN tenants t ON t.id=r.tenant_id')
        assert len(recordings)==1 and recordings[0]['slug']=='alpha'
        with wave.open(io.BytesIO(recordings[0]['audio']),'rb') as audio:
            assert audio.getframerate()==8000 and audio.getnframes()>0
            assert any(audio.readframes(audio.getnframes()))
        other=created[1]['id']
        from fastapi import HTTPException
        try:
            await b.voice_records.audio_for_owner(other,recordings[0]['session_id'])
            raise AssertionError('Foreign recording exposed')
        except HTTPException as exc:
            assert exc.status_code==404
        copies=await pool.fetch("SELECT * FROM outbox WHERE kind='voice_recording_copy'")
        assert len(copies)==1 and copies[0]['tenant_id']==created[0]['id'] and copies[0]['to_addr']=='+64215550222'
        print('PASS: consent-gated telephone WAV saved to own CRM; withdrawal discards; cross-business read404; requested recording SMS queued once; real sends=0')
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
