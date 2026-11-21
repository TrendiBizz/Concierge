"""Actual CRM capture/isolation on an owned disposable database; no provider traffic."""
import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.update(DATABASE_URL=f"postgresql://postgres:test@127.0.0.1:{os.environ.get('CONCIERGE_TEST_POSTGRES_PORT', '55432')}/postgres",
                  ADMIN_TOKEN="release-qa", OUTBOX_ENABLED="false")
from fastapi.testclient import TestClient
from app import chat, convo, db, enquiries, inbound_email, tenants, tools
from app.main import app, _sms_reply

checks = 0
def check(value, message):
    global checks
    assert value, message
    checks += 1
    print("PASS", message)

with TestClient(app) as client:
    async def exercise():
        a = await tenants.create("Release QA A", None, slug="release-qa-a")
        b = await tenants.create("Release QA B", None, slug="release-qa-b")
        results = await asyncio.gather(*(enquiries.capture(a, "email", "same-event", "Hello", email="test@example.invalid") for _ in range(6)))
        check(len({r["id"] for r in results}) == 1, "Concurrent provider replay creates one enquiry")
        other = await enquiries.capture(b, "email", "same-event", "Other business", email="other@example.invalid")
        check(other["id"] != results[0]["id"], "Event identity is tenant scoped")
        first = await inbound_email.ingest_verified(a["id"], "cloudflare", "email-event-1", "sender@example.invalid", "admin@example.invalid", "Quote enquiry", "Please send a quote.")
        second = await inbound_email.ingest_verified(a["id"], "cloudflare", "email-event-1", "sender@example.invalid", "admin@example.invalid", "Quote enquiry", "Please send a quote.")
        check(first["id"] == second["id"], "Inbound email retry reuses its review draft")
        check(await db.pool().fetchval("SELECT count(*) FROM leads WHERE tenant_id=$1 AND email='sender@example.invalid'", a["id"]) == 1, "Inbound email captured in CRM without model call")
        with patch.object(chat, "run_turn", new_callable=AsyncMock, side_effect=RuntimeError("Synthetic AI outage")):
            reply = await _sms_reply(a, "+64215550123", "Can I book a service?", False)
        check("trouble" in reply, "SMS failure returns fallback")
        lead = await db.pool().fetchrow("SELECT * FROM leads WHERE tenant_id=$1 AND channel='sms'", a["id"])
        check(bool(lead), "SMS enquiry survives AI outage")
        ctx = {"conversation_id": lead["conversation_id"], "channel": "sms", "sms_inbound": True}
        await tools.run_tool(a, "capture_lead", {"name": "QA caller", "phone": "+64215550123", "message": "Booking request"}, ctx)
        check(await db.pool().fetchval("SELECT count(*) FROM leads WHERE tenant_id=$1 AND channel='sms'", a["id"]) == 1, "AI contact capture enriches existing enquiry")
        check(await db.pool().fetchval("SELECT count(*) FROM tasks WHERE tenant_id=$1 AND lead_id=$2", a["id"], lead["id"]) == 1, "Captured enquiry has one follow-up task")
        return a,b,lead
    a,b,lead = client.portal.call(exercise)
    tokens = []
    for tenant,role in [(a,"owner"),(b,"owner"),(a,"viewer")]:
        email = role + "@example.invalid"
        invitation = client.post('/admin/tenants/'+tenant['slug']+'/owner-invitations', headers={'X-Admin-Token':'release-qa'}, json={'email':email,'role':role}).json()
        client.post('/owner/auth/redeem', json={'token':invitation['invitation_token'],'password':'ReleaseQaPassphrase123!'})
        login = client.post('/owner/auth/login', json={'slug':tenant['slug'],'email':email,'password':'ReleaseQaPassphrase123!'}).json()
        tokens.append({'Authorization':'Bearer '+login['access_token']})
    overview = client.get('/owner/crm',headers=tokens[0])
    check(overview.status_code==200 and len(overview.json()['leads'])==3, "Owner sees own email and SMS enquiries")
    check(len(client.get('/owner/crm',headers=tokens[1]).json()['leads'])==1, "Other owner sees only their own enquiries")
    path='/owner/crm/leads/'+str(lead['id'])
    check(client.patch(path,headers=tokens[1],json={'status':'won'}).status_code==404, "Cross-tenant status change denied")
    check(client.patch(path,headers=tokens[2],json={'status':'won'}).status_code==403, "Viewer cannot change enquiry")
    check(client.patch(path,headers=tokens[0],json={'status':'contacted'}).status_code==200, "Owner can progress CRM enquiry")
    check(client.get('/owner/crm').status_code==401, "Anonymous CRM access denied")
print(f"ENQUIRY_CRM_PASS: {checks} checks")
