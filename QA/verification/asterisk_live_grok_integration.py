"""Real Asterisk → bridge → live Grok → disposable Concierge DB.
Synthetic calls only; no carrier call or message delivery. Needs local Docker,
macOS say, ffmpeg and an existing XAI_API_KEY. Uses fixture tenants from DB test.
"""
import asyncio
import ipaddress
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import uuid
import shutil
from contextlib import asynccontextmanager
import json
import base64
import re

from app import asterisk_bridge as b, db
from app.config import get_settings


def command(*args):
    result=subprocess.run(args,capture_output=True,text=True,check=True)
    return result.stdout.strip()


async def main():
    cfg=get_settings()
    assert 'fixture-only' in cfg.database_url
    # Read only the existing xAI credential; never expose it to Docker/CLI/logs.
    if not cfg.xai_api_key:
        source=Path(__file__).resolve().parents[2]/'concierge-stack/.env'
        for line in source.read_text().splitlines():
            if line.startswith('XAI_API_KEY='):
                cfg.xai_api_key=shlex.split(line.split('=',1)[1],comments=True)[0]
    assert cfg.xai_api_key, 'Existing Grok key required'
    cfg.phone_receptionist_enabled=True
    cfg.xai_realtime_url='wss://api.x.ai/v1/realtime'
    await db.init()
    before=await db.pool().fetchval('SELECT count(*) FROM phone_calls')
    servers=[]
    active=set()
    temp=tempfile.TemporaryDirectory(prefix='concierge-asterisk-')
    directory=Path(temp.name)
    name='concierge-asterisk-live-qa'
    connect=b.websockets.connect
    probes=[]
    class Probe:
        def __init__(self,ws):self.ws=ws;self.audio=bytearray();self.output_bytes=0;probes.append(self)
        async def send(self,value):
            event=json.loads(value)
            if event['type']=='input_audio_buffer.append':self.audio.extend(base64.b64decode(event['audio']))
            await self.ws.send(value)
        def __aiter__(self):return self
        async def __anext__(self):
            try:
                value=await self.ws.recv()
            except b.websockets.ConnectionClosedOK:
                raise StopAsyncIteration
            event=json.loads(value)
            if event['type'] in ('response.output_audio.delta','response.audio.delta'):
                self.output_bytes+=len(base64.b64decode(event['delta']))
            if event['type']=='session.updated':print('NEGOTIATED',event.get('session',{}).get('audio'),flush=True)
            if 'transcript' in event:print('TRANSCRIPT',event['type'],event.get('item_id'),event.get('transcript'),flush=True)
            return value
    @asynccontextmanager
    async def probe_connect(*args,**kwargs):
        async with connect(*args,**kwargs) as ws:
            yield Probe(ws)
    b.websockets.connect=probe_connect
    try:
        lines=['[general]','static=yes','writeprotect=yes','[qa]']
        caller=['[caller]']
        identities=[]
        for index,business in enumerate(('alpha','beta')):
            route=b.Route(business,f'+649555010{index}',9101+index)
            async def connected(reader,writer,route=route):
                # Fixture only: host listener reachable by Docker Desktop.
                task=asyncio.create_task(b.handle(reader,writer,route,[ipaddress.ip_network('0.0.0.0/0')]))
                active.add(task)
                task.add_done_callback(active.discard)
            server=await asyncio.start_server(connected,'0.0.0.0',0)
            servers.append(server)
            ident=str(uuid.uuid4());identities.append('ast:'+ident)
            port=server.sockets[0].getsockname()[1]
            message=f'This is a synthetic test call for {business}. Please take a message. The test order reference is {business} seven four two. Please save this message for the owner. Thank you. Goodbye.'
            command('say','-v','Samantha','-o',str(directory/f'{business}.aiff'),message)
            command('ffmpeg','-y','-loglevel','error','-i',str(directory/f'{business}.aiff'),'-ar','8000','-ac','1','-c:a','pcm_s16le',str(directory/f'{business}.wav'))
            lines += [f'exten => {business},1,Answer()',f' same => n,AudioSocket({ident},host.docker.internal:{port})',' same => n,Hangup()']
            caller += [f'exten => {business},1,Answer()',f' same => n,MixMonitor(/qa/{business}-received.wav)',
                       ' same => n,Wait(4)',f' same => n,Playback(/qa/{business})',' same => n,Wait(20)',' same => n,Hangup()']
        (directory/'extensions.conf').write_text('\n'.join(lines+caller)+'\n')
        command('docker','run','-d','--name',name,'-v',f'{directory}:/qa','-v',f'{directory}/extensions.conf:/etc/asterisk/extensions.conf:ro','concierge-asterisk-test:local')
        ready=False
        for _ in range(180):
            await asyncio.sleep(.3)
            try:
                result=command('docker','exec',name,'asterisk','-rx','core show help channel originate')
                if 'Usage1:' in result:
                    ready=True
                    break
            except subprocess.CalledProcessError:
                pass
        assert ready, 'Asterisk did not finish booting'
        print(command('docker','exec',name,'asterisk','-rx','core show version'),flush=True)
        for business in ('alpha','beta'):
            command('docker','exec',name,'asterisk','-rx',f'channel originate Local/{business}@qa extension {business}@caller')
        async with asyncio.timeout(65):
            while True:
                count=await db.pool().fetchval('SELECT count(*) FROM phone_calls WHERE call_sid=ANY($1) AND ended_at IS NOT NULL',identities)
                if count==2:
                    break
                await asyncio.sleep(.25)
        for ident,business in zip(identities,('alpha','beta')):
            row=await db.pool().fetchrow('SELECT p.*,t.slug FROM phone_calls p JOIN tenants t ON t.id=p.tenant_id WHERE p.call_sid=$1',ident)
            turns=await db.pool().fetch("SELECT m.role,m.content FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.tenant_id=$1 AND c.session_id=$2 ORDER BY m.id",row['tenant_id'],ident)
            user=' '.join(t['content'] for t in turns if t['role']=='user')
            assistant=' '.join(t['content'] for t in turns if t['role']=='assistant')
            assert business in user.lower(),(business,'caller speech not transcribed',user,row['status'])
            assert 'owner' in user.lower() and ('seven four two' in user.lower() or '742' in re.sub(r'\D', '', user)), (business,'message truncated',user)
            assert len([t for t in turns if t['role']=='assistant']) >= 2,(business,'Grok did not respond after caller message',assistant,row['status'])
            assert row['slug']==business
            queued=await db.pool().fetchval('SELECT count(*) FROM outbox WHERE tenant_id=$1 AND dedupe_key=$2',row['tenant_id'],ident+':owner')
            assert queued==1,(business,'owner notification not queued')
            assert (directory/f'{business}-received.wav').stat().st_size>1000
            print(f'PASS {business}: actual Asterisk audio → live Grok caller/assistant transcripts → own CRM → owner SMS queued once; call status={row["status"]}')
            print('Grok:',assistant[:350])
        assert await db.pool().fetchval('SELECT count(*) FROM phone_calls')==before+2
        assert all(p.output_bytes>1600 for p in probes), 'Missing returned Grok speech audio'
        print('PASS real Asterisk and live Grok, two concurrent businesses; carrier calls=0, external messages=0')
    except Exception:
        try:
            print(command('docker','logs','--tail','45',name))
        except Exception:
            pass
        raise
    finally:
        artifacts=Path('/tmp/concierge-asterisk-fixture-audio')
        artifacts.mkdir(exist_ok=True)
        for i,probe in enumerate(probes):
            (artifacts/f'input-{i}.raw').write_bytes(probe.audio)
        b.websockets.connect=connect
        for wav in directory.glob('*.wav'):
            shutil.copy2(wav,artifacts/wav.name)
        subprocess.run(['docker','rm','-f',name],capture_output=True)
        for server in servers:
            server.close();await server.wait_closed()
        for task in list(active):task.cancel()
        await asyncio.gather(*active,return_exceptions=True)
        await db.close()
        temp.cleanup()

asyncio.run(main())
