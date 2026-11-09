import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import mobile_connections as m


def test_mobile_forwarding_codes_are_for_actual_destination_and_requested_mode():
    steps=m.forwarding_steps('+6495550100','spark_nz','unanswered')
    assert [s['dial'] for s in steps]==['*61*+6495550100*11#','*67*+6495550100*11#']
    assert 'tel_url' not in steps[0]  # iPhone blocks forwarding codes in tel links.
    assert len(m.forwarding_steps('+6495550100','spark_nz','all_calls'))==1
    assert 'dial' not in m.forwarding_steps('+441234567890','other','all_calls')[0]


def test_owner_connection_is_scoped_and_does_not_claim_live_without_inbound_call(monkeypatch):
    row={'destination':'+6495550100','carrier':'spark_nz','created_at':datetime.now(timezone.utc),'answer_mode':'unanswered','designated_number':'+64215550100','connection':'mobile_forwarding'}
    fetch=AsyncMock(side_effect=[row,None])
    monkeypatch.setattr(m.db,'pool',lambda:SimpleNamespace(fetchrow=fetch))
    monkeypatch.setattr(m.channel_authorization,'is_authorized',AsyncMock(return_value=True))
    result=asyncio.run(m.mobile_connection({'tenant_id':'business-a','role':'owner'}))
    assert result['status']=='ready_to_forward' and result['last_call'] is None
    assert all(c.args[1]=='business-a' for c in fetch.await_args_list)


def test_owner_connection_never_exposes_another_business_or_unapproved_route(monkeypatch):
    monkeypatch.setattr(m.db,'pool',lambda:SimpleNamespace(fetchrow=AsyncMock(return_value=None)))
    assert asyncio.run(m.mobile_connection({'tenant_id':'business-b'}))=={'status':'destination_needed','steps':[]}
    row={'destination':'+6495550100','carrier':'spark_nz','created_at':None,'answer_mode':'all_calls','designated_number':'+64215550100','connection':'mobile_forwarding'}
    monkeypatch.setattr(m.db,'pool',lambda:SimpleNamespace(fetchrow=AsyncMock(return_value=row)))
    monkeypatch.setattr(m.channel_authorization,'is_authorized',AsyncMock(return_value=False))
    assert asyncio.run(m.mobile_connection({'tenant_id':'business-b'}))=={'status':'authorization_needed','steps':[]}


def test_owner_cannot_bind_a_forwarding_number_or_activate_a_business(monkeypatch):
    import httpx
    from app.main import app
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'admin_token','fixture-admin-only')
    async def auth():return {'tenant_id':'business-a','role':'owner'}
    app.dependency_overrides[m.owner_auth.current_user]=auth
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
            return await client.put('/admin/tenants/business-b/mobile-connection',json={'destination':'+6495550100'})
    try:
        assert asyncio.run(scenario()).status_code==401
    finally:app.dependency_overrides.clear()


def test_no_country_or_customer_inherits_the_spark_carrier_instructions():
    for number in ('+64215550100','+442079460000','+12125550100'):
        steps=m.forwarding_steps(number,'other','unanswered')
        assert all('dial' not in step for step in steps)
        assert steps[0]['destination']==number
    assert m.MobileConnection(destination='+6495550100').carrier=='other'
