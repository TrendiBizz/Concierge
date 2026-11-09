"""Run inside the deployed API container. Existing paid Grok only.
Creates disposable isolated tenants without notification destinations or channel
permissions. No SMS, email, calendar mutation or invitation is authorized here.
"""
import asyncio
import base64
import json
import uuid
import httpx
import websockets
from app import chat, db, ingest, tenants, voice
from app.public_fetch import PublicClient


async def main():
    await db.init()
    fixtures=[]
    try:
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            result=await PublicClient(client,'example.com').get('https://example.com/')
            assert result.status_code==200 and 'Example Domain' in result.text
            print('PASS actual public HTTPS fetch uses validated pinned destination',flush=True)
        suffix=uuid.uuid4().hex[:10]
        for label,phrase in (('A','amber seven four two'),('B','violet nine six one')):
            tenant=await tenants.create('Portal live fixture '+label,'https://example.invalid',slug='portal-live-'+suffix+'-'+label.lower())
            fixtures.append(tenant)
            assert not tenant.get('notify_email') and not tenant.get('notify_phone')
            await ingest.ingest_text(tenant,'live-qa','The private service reference for this business is '+phrase+'. This is synthetic test information. Do not request or send email, SMS, or calendar invitations.',title='Synthetic service reference')
            result=await chat.run_turn(tenant,'live-chat-'+suffix,'chat','What is the private service reference for this business?')
            assert phrase in result['reply'].lower(), result['reply']
            assert ('violet' if label=='A' else 'amber') not in result['reply'].lower()
            print('PASS live Grok chat answers only business '+label+' knowledge',flush=True)
            turns=await db.pool().fetchval('SELECT count(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.tenant_id=$1',tenant['id'])
            assert turns>=2
        tenant=fixtures[0]
        tenant.update(await tenants.update(tenant['slug'],{'voice_enabled':True}))
        minted=await voice.mint_token(tenant)
        session=minted['session'];session['instructions']='You are testing a synthetic website voice session. Say exactly: Portal voice test complete. Do not call any tools.';session['tools']=[]
        token=minted['token'];protocol=token if token.startswith('xai-client-secret.') else 'xai-client-secret.'+token
        audio=0;transcript=''
        async with asyncio.timeout(40):
            async with websockets.connect(minted['url'],subprotocols=[protocol]) as ws:
                await ws.send(json.dumps({'type':'session.update','session':session}))
                await ws.send(json.dumps({'type':'conversation.item.create','item':{'type':'message','role':'user','content':[{'type':'input_text','text':'Please say the voice test sentence now.'}]}}))
                await ws.send(json.dumps({'type':'response.create'}))
                async for raw in ws:
                    event=json.loads(raw);kind=event.get('type','')
                    if kind in ('response.audio.delta','response.output_audio.delta'):audio+=len(base64.b64decode(event['delta']))
                    if kind in ('response.audio_transcript.done','response.output_audio_transcript.done'):transcript=event.get('transcript','')
                    if kind=='error':raise AssertionError('Grok rejected voice session')
                    if kind=='response.done':break
        assert audio>1000 and 'test' in transcript.lower(), (audio,transcript)
        print('PASS live website-protocol Grok ephemeral-token session returns audio and transcript; bytes='+str(audio),flush=True)
        assert not await db.pool().fetchval('SELECT 1 FROM outbox WHERE tenant_id=ANY($1::uuid[])',[t['id'] for t in fixtures])
        print('PASS synthetic live checks created zero outbound messages or calendar invitations',flush=True)
    finally:
        for tenant in fixtures:
            await db.pool().execute('DELETE FROM tenants WHERE id=$1',tenant['id'])
        await db.close()
        print('REMOVED disposable live fixtures',flush=True)


if __name__=='__main__':asyncio.run(main())
