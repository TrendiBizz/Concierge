"""Real disposable PostgreSQL/API acceptance. Google/LLM boundaries are fixtures.
No real SMS, email, calendar event, invitation or purchase is made.
"""
import asyncio
import io
import json
import tempfile
import uuid
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from app import chat, email_secretary, acknowledgements, booking, calendar_connection as calendar, convo, db, enquiries, inbound_email, owner_auth, quotations, tenants, voice_records
from app.config import get_settings
from app.main import app


async def main():
    await db.init()
    checks = []
    def check(label, condition):
        assert condition, label
        checks.append(label)
        print('PASS', label)
    a = await tenants.create('Portal fixture A', 'https://a.example', slug='portal-fixture-a')
    b = await tenants.create('Portal fixture B', 'https://b.example', slug='portal-fixture-b')
    try:
        for tenant, digit in ((a, '1'), (b, '2')):
            saved = await tenants.update(tenant['slug'], {'notify_email': digit+'@example.invalid', 'notify_phone': '+6421555010'+digit,
                'sms_enabled': True, 'native_booking': True, 'timezone': 'Pacific/Auckland',
                'business_hours': {d: [['08:00', '18:00']] for d in booking.DAYS}, 'min_notice_hours': 0})
            tenant.update(saved)
            for channel in ('sms_send', 'email_send', 'call_recording', 'email_read'):
                await db.pool().execute('INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES($1,$2,true,$3)', tenant['id'], channel, uuid.uuid4())
        ca, cb = await asyncio.gather(*(convo.get_or_create(t, 'fixture-chat-123', 'chat', None, None) for t in (a, b)))
        long_email = 'Subject: Fixture\n\n' + ('Original enquiry details. ' * 220)
        leads = await asyncio.gather(enquiries.capture(a, 'chat', 'chat-event', 'A wants a quote', conversation_id=ca),
                                     enquiries.capture(b, 'chat', 'chat-event', 'B wants a quote', conversation_id=cb))
        la, lb = leads
        await enquiries.capture(a, 'chat', 'chat-event', 'A wants a quote', conversation_id=ca)
        check('same event and two businesses: exactly one enquiry per business', await db.pool().fetchval("SELECT count(*) FROM leads WHERE tenant_id=ANY($1::uuid[])", [a['id'], b['id']]) == 2)
        owner_rows = await db.pool().fetch('SELECT * FROM outbox WHERE tenant_id=$1', a['id'])
        check('scoring reload cannot duplicate an ingress owner alert', len(owner_rows) == 2)
        check('owner email and SMS target only that business', {r['to_addr'] for r in owner_rows} == {a['notify_email'], a['notify_phone']})
        check('contact consent never creates an unrequested acknowledgement', not await db.pool().fetchval("SELECT 1 FROM outbox WHERE kind='enquirer_ack'"))
        declined = await acknowledgements.request(a, {'requested': False}, {'conversation_id': ca})
        check('declined acknowledgement sends nothing', declined['status'] == 'declined' and not await db.pool().fetchval("SELECT 1 FROM outbox WHERE kind='enquirer_ack'"))
        ack = {'requested': True, 'channel': 'email', 'recipient': 'caller@example.invalid', 'confirmed': True}
        check('acknowledgement cannot skip readback', (await acknowledgements.request(a, ack, {'conversation_id': ca}))['needs_confirmation'])
        await acknowledgements.request(a, ack, {'conversation_id': ca})
        await acknowledgements.request(a, ack, {'conversation_id': ca})
        check('confirmed acknowledgement is deduplicated separately from owner notices', await db.pool().fetchval("SELECT count(*) FROM outbox WHERE kind='enquirer_ack'") == 1)
        check('foreign conversation cannot request acknowledgement', not (await acknowledgements.request(b, ack, {'conversation_id': ca}))['ok'])
        current = {'tenant_id': a['id'], 'slug': a['slug'], 'id': uuid.uuid4(), 'role': 'owner'}
        app.dependency_overrides[owner_auth.current_user] = lambda: current.copy()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
            draft = {'lead_id': str(la['id']), 'title': 'Fixture quote', 'currency': 'NZD', 'tax_basis_points': 1500,
                     'lines': [{'description': 'Service', 'quantity': '1.5', 'unit_price_cents': 10001}]}
            response = await client.post('/owner/crm/quotations', json=draft)
            check('quotation API creates a draft with decimal rounding and explicit tax', response.status_code == 201 and response.json()['total_cents'] == 17252)
            quote = response.json()
            current.update(tenant_id=b['id'], slug=b['slug'])
            check('foreign quotations are invisible', (await client.get('/owner/crm/quotations')).json() == [])
            check('foreign enquiry cannot be attached to quotation', (await client.post('/owner/crm/quotations', json=draft)).status_code == 404)
            check('foreign quote cannot be changed', (await client.post('/owner/crm/quotations/'+quote['id']+'/status', json={'status': 'reviewed', 'version': 1})).status_code == 409)
            current.update(tenant_id=a['id'], slug=a['slug'], role='editor')
            check('editor cannot approve quotation', (await client.post('/owner/crm/quotations/'+quote['id']+'/status', json={'status': 'reviewed', 'version': 1})).status_code == 403)
            current['role'] = 'owner'
            response = await client.post('/owner/crm/quotations/'+quote['id']+'/status', json={'status': 'reviewed', 'version': 1})
            check('owner reviews quotation without sending', response.status_code == 200 and response.json()['status'] == 'reviewed')
            check('reviewed price snapshot cannot be edited', (await client.put('/owner/crm/quotations/'+quote['id'], json=draft)).status_code == 409)
            check('stale quotation status update is rejected', (await client.post('/owner/crm/quotations/'+quote['id']+'/status', json={'status': 'accepted', 'version': 1})).status_code == 409)
        # Full original email is persisted outside the 1000-character CRM summary.
        mail = await inbound_email.ingest_verified(a['id'], 'cloudflare', 'fixture@example.invalid', 'sender@example.invalid', 'inbox@example.invalid', 'Fixture email', long_email)
        await inbound_email.ingest_verified(a['id'], 'cloudflare', 'fixture@example.invalid', 'sender@example.invalid', 'inbox@example.invalid', 'Fixture email', long_email)
        check('email webhook replay keeps one draft and full original email', await db.pool().fetchval('SELECT count(*) FROM email_drafts WHERE tenant_id=$1', a['id']) == 1 and await db.pool().fetchval("SELECT max(length(original_text)) FROM enquiry_sources WHERE tenant_id=$1 AND channel='email'", a['id']) > 4000)
        check('manual email mode never queues an automatic reply', not await db.pool().fetchval('SELECT 1 FROM email_secretary_jobs WHERE tenant_id=$1', a['id']))
        complete_mail = 'Subject: ' + 'S'*250 + '\n\n' + 'x'*19980 + 'END OF ORIGINAL EMAIL'
        await convo.save_message(ca, 'user', complete_mail)
        saved = await db.pool().fetchval('SELECT content FROM messages WHERE conversation_id=$1 ORDER BY id DESC LIMIT 1',ca)
        check('maximum-length email with subject retains its complete final content', saved == complete_mail)
        # Consent-gated real WAV bytes, owner recording link, and retry safety.
        state = await voice_records.start(a, 'fixture-voice-123', record=True)
        session = await voice_records.authenticate(uuid.UUID(state['id']), state['token'])
        await convo.save_message(session['conversation_id'], 'user', 'I need a quotation for a service.')
        await convo.save_message(session['conversation_id'], 'assistant', 'The owner can review a quotation. Would you like an acknowledgement?')
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000); audio.writeframes(b'\0\0' * 800)
        await voice_records.store_audio(session, wav.getvalue(), 'audio/wav')
        result = await voice_records.finish(session, a)
        await voice_records.finish(session, a)
        rows = await db.pool().fetch("SELECT * FROM outbox WHERE tenant_id=$1 AND dedupe_key LIKE 'voice-finished:%'", a['id'])
        check('voice completion saves original dialogue and recording link to both owner channels once', len(rows) == 2 and all('Concierge:' in r['body'] and '/recordings/shared/' in r['body'] for r in rows))
        try:
            await voice_records.audio_for_owner(b['id'], session['id'])
            raise AssertionError('foreign audio accessible')
        except Exception as error:
            check('foreign business cannot read recording', getattr(error, 'status_code', None) == 404)
        try:
            await voice_records.store_audio({**session, 'recording_consent': False}, wav.getvalue(), 'audio/wav')
            raise AssertionError('unconsented recording stored')
        except Exception as error:
            check('recording consent is enforced at storage', getattr(error, 'status_code', None) == 403)
        # Simulated Google provider, real database/booking transaction. Never calls Google.
        await db.pool().execute("INSERT INTO calendar_connections(tenant_id) VALUES($1),($2)", a['id'], b['id'])
        remote = {}; requests = []; busy_windows = []; timeout_insert = set()
        async def provider(tenant_id, method, path, **kwargs):
            requests.append((str(tenant_id), method, path, kwargs))
            if path == '/freeBusy':
                return httpx.Response(200, json={'calendars': {'primary': {'busy': busy_windows}}})
            identity = (str(tenant_id), path.rsplit('/', 1)[-1])
            if method == 'GET':
                return httpx.Response(200, json=remote[identity]) if identity in remote else httpx.Response(404)
            if method == 'POST':
                payload = kwargs['json']; identity = (str(tenant_id), payload['id']); remote[identity] = payload
                if tenant_id in timeout_insert:
                    timeout_insert.remove(tenant_id)
                    raise httpx.ReadTimeout('fixture provider accepted before timeout')
                check('calendar insert requests guest invitations', kwargs.get('params') == {'sendUpdates': 'all'})
                return httpx.Response(201, json=payload)
            if method == 'DELETE':
                remote.pop(identity, None); return httpx.Response(204)
            raise AssertionError((method, path))
        with patch.object(calendar, 'request', provider):
            day = datetime.now(timezone.utc).astimezone(booking.ZoneInfo(a['timezone'])).date() + timedelta(days=2)
            slots = (await booking.availability(a, str(day)))['slots']
            start = str(day)+' '+slots[0]
            contexts = [{'conversation_id': await convo.get_or_create(a, 'fixture-booking-'+str(i), 'chat', None, None), 'channel': 'chat'} for i in range(2)]
            args = {'name': 'Fixture Enquirer', 'email': 'booker@example.invalid', 'start': start, 'consent_to_contact': True}
            for ctx in contexts:
                check('booking requires readback', (await booking.book(a, args, ctx))['needs_confirmation'])
            results = await asyncio.gather(*(booking.book(a, {**args, 'confirmed': True}, ctx) for ctx in contexts))
            success = next(r for r in results if r['ok'])
            check('concurrent booking conflict permits one calendar booking', sum(r['ok'] for r in results) == 1 and success['calendar_state'] == 'synced')
            check('calendar event contains only correct tenant and attendee', len(remote) == 1 and all(k[0] == str(a['id']) and e['attendees'] == [{'email': args['email']}] for k,e in remote.items()))
            winner = next(ctx for r,ctx in zip(results, contexts) if r['ok'])
            again = await booking.book(a, {**args, 'confirmed': True}, winner)
            check('duplicate confirmed booking returns existing event without duplicate', again['duplicate'] and len(remote) == 1)
            check('same slot remains available to other business', slots[0] in (await booking.availability(b, str(day)))['slots'])
            # Existing calendar conflict is checked before exposing a free slot.
            moment = datetime.fromisoformat(start).replace(tzinfo=booking.ZoneInfo(a['timezone'])).astimezone(timezone.utc)
            busy_windows[:] = [{'start': moment.isoformat(), 'end': (moment+timedelta(minutes=a['slot_minutes'])).isoformat()}]
            check('external busy calendar blocks offered slot', slots[0] not in (await booking.availability(b, str(day)))['slots'])
            busy_windows.clear()
            # Ambiguous timeout: remote event exists, DB marks retry, next GET reconciles.
            timeout_insert.add(b['id'])
            ctx = {'conversation_id': cb, 'channel': 'chat'}
            await booking.book(b, args, ctx)
            pending = await booking.book(b, {**args, 'confirmed': True}, ctx)
            check('provider timeout never claims confirmed calendar/invitation', pending['booking_status'] == 'pending_calendar' and pending['calendar_state'] == 'retry')
            before = len([r for r in requests if r[1] == 'POST' and r[2].endswith('/events')])
            await calendar.sync_one(uuid.UUID(pending['appointment_id']))
            after = len([r for r in requests if r[1] == 'POST' and r[2].endswith('/events')])
            check('retry reconciles accepted remote event without another insert/invite', before == after and await db.pool().fetchval('SELECT calendar_state FROM appointments WHERE id=$1', uuid.UUID(pending['appointment_id'])) == 'synced')
            await db.pool().execute("UPDATE appointments SET status='cancelled' WHERE id=$1", uuid.UUID(pending['appointment_id']))
            await calendar.sync_one(uuid.UUID(pending['appointment_id']))
            check('cancellation removes remote event and records result', len(remote) == 1 and await db.pool().fetchval('SELECT calendar_state FROM appointments WHERE id=$1', uuid.UUID(pending['appointment_id'])) == 'cancelled')
        # Explicit automatic-email opt-in, replay dedupe, and human review exclusion.
        await tenants.update(a['slug'], {'email_auto_reply': True})
        automated = await inbound_email.ingest_verified(a['id'], 'cloudflare', 'auto-fixture-1', 'auto@example.invalid', 'inbox@example.invalid', 'Automatic fixture', 'Please explain your services')
        from unittest.mock import AsyncMock
        model = AsyncMock(return_value={'reply':'Fixture answer using only this business knowledge'})
        with patch.object(chat, 'run_turn', model):
            await email_secretary.process_once()
            await email_secretary.process_once()
        check('opted-in email answers exactly once to the original sender', model.await_count == 1 and await db.pool().fetchval("SELECT count(*) FROM outbox WHERE tenant_id=$1 AND kind='email_secretary_reply' AND to_addr='auto@example.invalid'", a['id']) == 1)
        check('automatic reply removes duplicate manual-send draft', await db.pool().fetchval('SELECT status FROM email_drafts WHERE id=$1', automated['id']) == 'discarded')
        reviewed = await inbound_email.ingest_verified(a['id'], 'cloudflare', 'auto-fixture-2', 'manual@example.invalid', 'inbox@example.invalid', 'Manual first', 'Owner handles this')
        await db.pool().execute("UPDATE email_drafts SET status='approved' WHERE id=$1", reviewed['id'])
        with patch.object(chat, 'run_turn', model):
            await email_secretary.process_once()
        check('human-reviewed email cannot also trigger an automatic answer', model.await_count == 1 and not await db.pool().fetchval("SELECT 1 FROM outbox WHERE kind='email_secretary_reply' AND to_addr='manual@example.invalid'"))
        revoked = await inbound_email.ingest_verified(a['id'], 'cloudflare', 'auto-fixture-3', 'revoked@example.invalid', 'inbox@example.invalid', 'Revoked fixture', 'Do not auto answer')
        await db.pool().execute("UPDATE tenant_channel_authorizations SET authorized=false WHERE tenant_id=$1 AND channel='email_send'", a['id'])
        with patch.object(chat, 'run_turn', model):
            await email_secretary.process_once()
        check('email permission revocation holds work before model or reply', model.await_count == 1 and await db.pool().fetchval("SELECT status FROM email_secretary_jobs WHERE tenant_id=$1 AND sender='revoked@example.invalid'",a['id']) == 'held')
        # Existing CRM rows have no permission to replay calendar invitations.
        legacy = await db.pool().fetchval("INSERT INTO appointments(tenant_id,starts_at,ends_at,name,email,consent_contact) VALUES($1,now()+interval '4 days',now()+interval '4 days 30 minutes','Legacy fixture','legacy@example.invalid',true) RETURNING id",a['id'])
        external = AsyncMock(side_effect=AssertionError('Legacy appointment reached provider'))
        with patch.object(calendar,'request',external):
            await calendar.sync_one(legacy)
        check('calendar connection cannot replay existing CRM appointments', external.await_count == 0)
        check('no quotation automatically creates an outbound quote message', not await db.pool().fetchval("SELECT 1 FROM outbox WHERE kind LIKE '%quote%'"))
        print(f'PORTAL_ACCEPTANCE_PASS: {len(checks)} checks; actual PostgreSQL/API, fixture Google boundary; zero external deliveries')
    finally:
        app.dependency_overrides.clear()
        for tenant in (a,b):
            await tenants.delete(tenant['slug'])
        await db.close()
        print('REMOVED synthetic tenants and all fixture CRM/queue/recording data')


asyncio.run(main())
