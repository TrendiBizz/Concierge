"""Create one empty local workspace and load actual website text once. No LLM calls."""
import json
import os
from pathlib import Path
import urllib.request

from trafilatura import extract

HEADERS = {'Content-Type': 'application/json', 'X-Admin-Token': os.environ['ADMIN_TOKEN']}


def api(path, body=None, method=None):
    request = urllib.request.Request('http://127.0.0.1:8000' + path, headers=HEADERS,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     method=method)
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


tenants = api('/admin/tenants')
tenant = next((t for t in tenants if t['slug'] == 'trendi-local'), None)
if tenant is None:
    tenant = api('/admin/tenants', {'slug': 'trendi-local', 'name': 'Trendi local workspace',
                 'site_url': 'https://trendibizz.com',
                 'allowed_origins': ['http://127.0.0.1:8793', 'http://localhost:8793'],
                 'greeting': 'Hi! Ask me about Trendi Concierge, SEO or security reviews.'})
    api('/admin/tenants/trendi-local', {
        'timezone': 'Pacific/Auckland', 'native_booking': True, 'sms_enabled': False,
        'voice_enabled': False, 'phone_enabled': False, 'campaigns_enabled': False,
        'business_hours': {day: [['09:00', '17:00']] for day in ('mon', 'tue', 'wed', 'thu', 'fri')},
    }, method='PATCH')

# One atomic document also makes an interrupted first start recoverable. Never
# overwrite business information after the operator has saved their own content.
detail = api('/admin/tenants/trendi-local')
if not detail.get('chunk_count'):
    pages = []
    for page in ('concierge', 'seo', 'penetration-testing'):
        text = extract(Path(f'/preview-site/{page}.html').read_text())
        if not text:
            raise RuntimeError('Website text extraction failed')
        pages.append(text)
    api('/admin/tenants/trendi-local/ingest-text',
        {'label': 'website-local', 'title': 'Trendi website', 'text': '\n\n'.join(pages)})

# Public widget key only; invitations, admin keys and report/calendar tokens stay private.
print(json.dumps({'slug': tenant['slug'], 'public_key': tenant['public_key']}))
