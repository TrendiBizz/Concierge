"""The same caller gives contact consent after an ingress CRM enquiry exists."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import tools, automation


def test_contact_consent_does_not_send_unrequested_acknowledgement(monkeypatch):
    tenant={'id':'business-a','name':'Test Business','sms_enabled':True}
    lead={'id':7,'tenant_id':'business-a','conversation_id':'conversation-a','name':'Jo',
          'phone':'+64278817368','email':'','channel':'phone','message':'Please send details',
          'consent_contact':True,'consent_marketing':False}
    # capture_lead now reconciles the caller into a customer case before writing the lead, so the
    # fake must model both calls. The consent behaviour under test is unchanged.
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value=lead), execute=AsyncMock())
    monkeypatch.setattr(tools.db,'pool',lambda:pool)
    monkeypatch.setattr(tools.casetimeline,'reconcile',AsyncMock(return_value={'id':'case-1'}))
    monkeypatch.setattr(tools,'get_settings',lambda:SimpleNamespace(default_country_code='64'))
    monkeypatch.setattr(automation,'get_settings',lambda:SimpleNamespace(default_country_code='64'))
    queue=AsyncMock(return_value=True)
    monkeypatch.setattr(automation.outbox,'enqueue',queue)
    monkeypatch.setattr(automation.events,'queue_twenty',AsyncMock())
    monkeypatch.setattr(automation.events,'emit',lambda *a,**k:None)
    result=asyncio.run(tools.run_tool(tenant,'capture_lead',{
        'phone':'+64278817368','name':'Jo','message':'Please send details',
        'consent_to_contact':True}, {'conversation_id':'conversation-a','channel':'phone'}))
    assert result['ok']
    assert queue.await_count==0, 'Contact consent is separate from requesting an acknowledgement'


def test_followup_requires_consent_and_does_not_text_inbound_sms_again(monkeypatch):
    tenant={'id':'business-a','name':'Test','sms_enabled':True}
    monkeypatch.setattr(automation,'get_settings',lambda:SimpleNamespace(default_country_code='64'))
    queue=AsyncMock();monkeypatch.setattr(automation.outbox,'enqueue',queue)
    async def run():
        for channel,consent in [('phone',False),('sms',True)]:
            await automation.lead_followup(tenant,{'id':7,'phone':'+64278817368','name':'Jo','channel':channel,'consent_contact':consent})
    asyncio.run(run());queue.assert_not_awaited()
