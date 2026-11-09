"""Run in candidate container against a disposable database; never sends anything."""
import asyncio,uuid
import asyncpg
from pathlib import Path
from app import db,voice_records as r,convo,tools
from app.config import get_settings

async def main():
 settings=get_settings();control=await asyncpg.connect(settings.database_url)
 name='qa_voice_'+uuid.uuid4().hex[:12];connection=None
 await control.execute('CREATE DATABASE '+name)
 try:
  connection=await asyncpg.connect(settings.database_url,database=name)
  await connection.execute(Path('/srv/app/schema.sql').read_text().replace('__DIM__',str(settings.embed_dim)))
  pool=await asyncpg.create_pool(settings.database_url,database=name,min_size=1,max_size=3)
  db._pool=pool
  tenant=dict(await pool.fetchrow("INSERT INTO tenants(slug,name,public_key,notify_email) VALUES('fixture','Fixture Business','pk-fixture','owner@example.invalid') RETURNING *"))
  await pool.execute("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,'call_recording',true,$2),($1,'sms_send',true,$2)",tenant['id'],uuid.uuid4())
  state=await r.start(tenant,'fixture-voice-123',record=True)
  session=await r.authenticate(uuid.UUID(state['id']),state['token'])
  await convo.save_message(session['conversation_id'],'user','Please send the information I requested')
  await convo.save_message(session['conversation_id'],'assistant','The team will follow up')
  for _ in range(2):
   captured=await tools.run_tool(tenant,'capture_lead',{'name':'Fixture caller','phone':'+64215550100','message':'Please send details','consent_to_contact':True},{'conversation_id':session['conversation_id'],'channel':'voice'})
   assert captured['ok']
  assert await pool.fetchval('SELECT count(*) FROM leads')==1, 'One voice enquiry per conversation'

  audio=Path('/tmp/recording-fixture.webm').read_bytes()
  assert (await r.store_audio(session,audio,'audio/webm'))['ok']
  assert (await r.store_audio(session,audio,'audio/webm'))['duplicate']
  requested=await r.request_delivery(session,tenant,channel='sms',content='recording',confirmed=True)
  assert requested['status']=='requested'
  assert await pool.fetchval("SELECT count(*) FROM outbox WHERE kind='voice_recording_copy'")==0
  result=await r.finish(session,tenant);lead=uuid.UUID(result['lead_id'])
  assert result['delivery']['status']=='queued'
  assert (await r.finish(session,tenant))['delivery']['status']=='already_queued'
  assert (await r.finish(session,tenant))['duplicate']
  assert await pool.fetchval('SELECT count(*) FROM leads')==1
  assert await pool.fetchval("SELECT count(*) FROM outbox WHERE dedupe_key LIKE 'voice-finished:%'")==1
  recordings=await r.recordings_for_lead(tenant['id'],lead);assert len(recordings)==1
  own=await r.audio_for_owner(tenant['id'],session['id']);assert bytes(own['audio'])==audio
  token=await r.share(tenant['id'],session['id']);assert bytes((await r.shared_audio(token))['audio'])==audio
  assert await pool.fetchval("SELECT count(*) FROM outbox WHERE kind='voice_recording_copy'")==1
  await pool.execute("UPDATE voice_recording_shares SET expires_at=now()-interval '1 second'")
  from fastapi import HTTPException
  try:await r.shared_audio(token);raise AssertionError('Expired link accepted')
  except HTTPException as error:assert error.status_code==404
  await pool.execute("UPDATE voice_recordings SET created_at=now()-interval '31 days'")
  await r.purge_expired();assert await pool.fetchval('SELECT count(*) FROM voice_recordings')==0
  print('PASS disposable DB: actual browser audio stored/read/shared, transcript CRM enquiry, completion notice, caller-requested delivery only after saving, deduplicated queue, expiry and retention')
  await pool.close();db._pool=None
 finally:
  if connection:await connection.close()
  await control.execute('DROP DATABASE '+name+' WITH (FORCE)');await control.close()
  print('REMOVED disposable database; no messages sent and no customer data changed')
asyncio.run(main())
