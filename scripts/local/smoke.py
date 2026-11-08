"""Exercise the actual isolated stack through its gateway. No paid/provider calls.

Run via: docker compose ... exec -T api python - < scripts/local/smoke.py
Only the randomly named businesses created by this run are removed.
"""
import asyncio
from datetime import datetime, timedelta
import secrets
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from app import booking, convo, db, tenants
from app.config import get_settings

s = get_settings()
assert s.public_base_url == 'http://127.0.0.1:8793'
assert urlsplit(s.database_url).path == '/trendi_local'
assert not s.outbox_enabled and not s.phone_receptionist_enabled
operator = {'X-Admin-Token': s.admin_token}
client = httpx.Client(base_url='http://web', timeout=180,
                      headers={'Host': '127.0.0.1:8793', 'Origin': s.public_base_url})
created = []
checks = 0


def check(condition, label):
    global checks
    if not condition:
        raise AssertionError(label)
    checks += 1
    print('PASS:', label, flush=True)


def request(method, path, *, data=None, headers=None, status=200):
    response = client.request(method, path, json=data, headers=headers)
    check(response.status_code == status, method + ' ' + path.split('?')[0].split('/calendar/')[0]
          if '/owner-invitations' not in path else 'Private owner invitation issued')
    return response


async def booking_checks(a_slug, b_slug):
    await db.init()
    try:
        a, b = await tenants.get_by_slug(a_slug), await tenants.get_by_slug(b_slug)
        for tenant in (a, b):
            await tenants.update(tenant['slug'], {
                'native_booking': True, 'timezone': 'Pacific/Auckland', 'min_notice_hours': 0,
                'max_days_ahead': 30, 'slot_minutes': 30,
                'business_hours': {day: [['09:00', '12:00']] for day in booking.DAYS},
            })
        a, b = await tenants.get_by_slug(a_slug), await tenants.get_by_slug(b_slug)
        day = (datetime.now(ZoneInfo('Pacific/Auckland')) + timedelta(days=2)).date()
        free = await booking.availability(a, str(day))
        check(free['ok'] and bool(free['slots']), 'Native booking availability')
        slot = free['slots'][0]
        args = {'start': f'{day} {slot}', 'name': 'Local QA Booking',
                'email': 'qa@example.invalid', 'confirmed': True}
        contexts = []
        for _ in range(2):
            cid = await convo.get_or_create(a, secrets.token_hex(12), 'chat', None, None)
            context = {'conversation_id': cid, 'channel': 'chat'}
            pending = await booking.book(a, args, context)
            check(pending.get('needs_confirmation') and not pending['ok'], 'Booking requires read-back')
            contexts.append(context)
        results = await asyncio.gather(*(booking.book(a, args, ctx) for ctx in contexts))
        check(sum(result['ok'] for result in results) == 1, 'Concurrent slot booked exactly once')
        check(slot in (await booking.availability(b, str(day)))['slots'], 'Other business calendar isolated')
        feed = client.get('/api/v1/calendar/' + a['calendar_token'] + '.ics')
        check(feed.status_code == 200 and 'Local QA Booking' in feed.text, 'Private ICS feed through website gateway')
        other = client.get('/api/v1/calendar/' + b['calendar_token'] + '.ics')
        check(other.status_code == 200 and 'Local QA Booking' not in other.text, 'Calendar feed contains only its business')
        pipeline = client.get('/admin/tenants/' + a_slug + '/pipeline', headers=operator)
        check(pipeline.status_code == 200 and 'Local QA Booking' in pipeline.text, 'Booked lead appears in office pipeline')
    finally:
        await db.close()


try:
    for path in ('/', '/concierge', '/concierge-start', '/seo', '/penetration-testing',
                 '/tools/site-check', '/admin-ui', '/owner-ui', '/healthz', '/widget.js'):
        request('GET', path)
    request('GET', '/_headers', status=404)
    request('GET', '/.env', status=404)
    request('GET', '/owner/onboarding', status=401)
    request('GET', '/admin/tenants', status=401)
    redirect = client.get('/concierge/sign-in')
    check(redirect.status_code == 302 and redirect.headers['location'].endswith('/owner-ui'),
          'Customer sign-in stays in the integrated stack')
    robots = request('GET', '/api/robots?url=https%3A%2F%2Ftrendibizz.com')
    check('User-agent' in robots.text, 'Original website worker serves the robots checker')
    request('POST', '/api/site-check', data={'url': 'http://127.0.0.1'}, status=400)
    request('POST', '/api/security-check', data={'url': 'http://127.0.0.1'}, status=400)
    suffix = secrets.token_hex(5)
    actors = []
    for letter in ('a', 'b'):
        tenant = request('POST', '/admin/tenants', headers=operator,
                         data={'slug': f'local-qa-{letter}-{suffix}',
                               'name': f'Local QA {letter} {suffix}'}).json()
        created.append(tenant['slug'])
        invitation = request('POST', f'/admin/tenants/{tenant["slug"]}/owner-invitations',
                              headers=operator, data={'email': f'{letter}@example.invalid', 'role': 'owner'},
                              status=201).json()
        check(invitation['invitation_url'].startswith(s.public_base_url + '/owner-ui#invite='),
              'Invitation opens this local owner portal')
        password = secrets.token_urlsafe(24)
        request('POST', '/owner/auth/redeem', data={'token': invitation['invitation_token'], 'password': password})
        request('POST', '/owner/auth/redeem', data={'token': invitation['invitation_token'], 'password': password}, status=400)
        login = request('POST', '/owner/auth/login', data={'slug': tenant['slug'],
                         'email': f'{letter}@example.invalid', 'password': password}).json()
        actors.append({'Authorization': 'Bearer ' + login['access_token']})
    a, b = actors
    request('PATCH', '/owner/onboarding/profile', headers=a,
            data={'name': 'Local QA Updated A', 'site_url': 'https://a.example.invalid'})
    separate = request('GET', '/owner/onboarding', headers=b).json()
    check(separate['business']['name'] != 'Local QA Updated A', 'Business profiles remain separate')
    doc = request('POST', '/owner/knowledge', headers=a, status=201,
                  data={'title': 'Local QA document', 'text': 'Local QA business opens on weekdays at nine.'}).json()
    own = request('GET', '/owner/knowledge', headers=a).json()
    check(any(d['document_id'] == doc['document_id'] for d in own), 'Knowledge saved with real embeddings')
    check(request('GET', '/owner/knowledge', headers=b).json() == [], 'Other business cannot see knowledge')
    request('DELETE', '/owner/knowledge/' + doc['document_id'], headers=b, status=404)
    request('GET', '/owner/social/status', headers=a)
    request('GET', '/owner/social/accounts', headers=a)
    request('POST', '/owner/knowledge', headers=a, status=201,
            data={'title': 'Local QA document', 'text': 'Local QA business now opens at ten.'})
    check(len(request('GET', '/owner/knowledge', headers=a).json()) == 1, 'Same-title document replaced atomically')
    asyncio.run(booking_checks(*created))
    request('POST', '/owner/auth/logout', headers=a)
    request('GET', '/owner/me', headers=a, status=401)
    request('GET', '/owner/me', headers=b)
    print(f'LOCAL_STACK_PASS: {checks} checks; no provider requests, calls, publishing or delivery.', flush=True)
finally:
    for slug in created:
        response = client.delete('/admin/tenants/' + slug, headers=operator)
        if response.status_code != 200:
            raise RuntimeError('Local QA workspace cleanup failed')
    client.close()
