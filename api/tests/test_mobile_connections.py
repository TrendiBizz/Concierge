import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app import call_forwarding as cf
from app import mobile_connections as m

NZ_DID='+6492431347'


def codes(steps,field='set'):
    return [s['dial'] for s in steps[field]]


class FakePool:
    """Answers fetchrow by a fragment of the SQL, and records the tenant id each query was scoped to."""
    def __init__(self,tenant=None,connection=None,call=None,saved=None):
        self.tenant={'default_country_code':'64','timezone':'Pacific/Auckland','notify_phone':'+64275550123','pref_country':None,'pref_carrier':None,'pref_answer_mode':None,**(tenant or {})}
        self.connection,self.call,self.args,self.executed=connection,call,[],[]
        self.saved=saved
    async def fetchrow(self,sql,*args):
        self.args.append(args[0])
        if 'FROM tenants t' in sql:return self.tenant
        if 'mobile_forwarding_connections' in sql:return self.connection
        if 'phone_calls' in sql:return self.call
    async def fetchval(self,sql,*args):return self.saved
    async def execute(self,sql,*args):self.executed.append((sql,args))
    @asynccontextmanager
    async def transaction(self):yield
    @asynccontextmanager
    async def acquire(self):yield self


def connection(**kw):
    return {'destination':NZ_DID,'carrier':'spark_nz','created_at':datetime.now(timezone.utc),'destination_country':'NZ','answer_mode':'unanswered','designated_number':'+64275550123','connection':'mobile_forwarding',**kw}


def use(monkeypatch,pool,authorized=True):
    monkeypatch.setattr(m.db,'pool',lambda:pool)
    monkeypatch.setattr(m.channel_authorization,'is_authorized',AsyncMock(return_value=authorized))


def owner(tenant='business-a'):
    return {'tenant_id':tenant,'role':'owner'}


def test_same_country_destination_is_dialled_in_national_format_never_plus_e164():
    steps=m.forwarding_steps(NZ_DID,'spark_nz','unanswered','NZ')
    assert codes(steps)==['*61*092431347*11#','*67*092431347*11#']  # the old bug dialled *61*+649...*11#
    assert not any('+' in c for c in codes(steps)+codes(steps,'check')+codes(steps,'cancel'))
    assert 'tel_url' not in steps['set'][0]  # iPhone blocks forwarding codes in tel links; the page builds links per device.
    assert len(m.forwarding_steps(NZ_DID,'spark_nz','all_calls','NZ')['set'])==1


@pytest.mark.parametrize('number,country,expected',[
    ('+442079460000','GB','02079460000'),
    ('+61291234567','AU','0291234567'),
    ('+12125550100','US','2125550100'),
    (NZ_DID,'NZ','092431347')])
def test_national_format_per_country_rule(number,country,expected):
    assert cf.dial_number(number,country)==expected
    assert codes(m.forwarding_steps(number,'other','all_calls',country))==['*21*'+expected+'#']


def test_cross_country_destination_is_international_not_a_bare_national_number():
    steps=m.forwarding_steps(NZ_DID,'other','all_calls','AU')
    assert codes(steps)==['*21*+6492431347#']
    assert cf.is_cross_country(NZ_DID,'AU') and not cf.is_cross_country(NZ_DID,'NZ')
    # Unknown owner country has no national rule, so it also stays international.
    assert codes(m.forwarding_steps(NZ_DID,'other','all_calls','ZZ'))==['*21*+6492431347#']


def test_unknown_carrier_and_country_get_the_gsm_standard_plus_ask_your_carrier():
    steps=m.forwarding_steps(NZ_DID,'no_such_carrier','unanswered','ZZ')
    assert [s['kind'] for s in steps['set']]==['no_answer','busy','unreachable']
    assert codes(steps)==['*61*+6492431347#','*67*+6492431347#','*62*+6492431347#']
    assert codes(steps,'check')==['*#61#','*#67#','*#62#']
    assert codes(steps,'cancel')==['##61#','##67#','##62#'] and steps['cancel_all']=='##002#'
    assert "ask your carrier" in steps['note'] and "Settings" in steps['note']
    assert codes(m.forwarding_steps(NZ_DID,'other','all_calls','NZ'),'check')==['*#21#']


def test_spark_keeps_its_published_11_suffix_but_other_nz_carriers_use_gsm_standard():
    s=m.forwarding_steps(NZ_DID,'spark_nz','all_calls','NZ')
    assert codes(s)==['*21*092431347*11#'] and codes(s,'check')==['*#21*11#']
    assert codes(s,'cancel')==['##21#']
    for carrier in ('one_nz','2degrees_nz'):
        assert codes(m.forwarding_steps(NZ_DID,carrier,'all_calls','NZ'))==['*21*092431347#']


def test_carrier_from_another_country_is_not_applied_and_unknown_ids_become_other():
    assert cf.normalize_carrier('spark_nz','AU')=='other'
    assert cf.normalize_carrier('spark_nz','NZ')=='spark_nz'
    assert cf.normalize_carrier('bogus')=='other'
    assert codes(m.forwarding_steps('+12125550100','verizon_us','all_calls','US'))==['*72' '2125550100']


def test_tenant_country_comes_from_code_then_timezone_and_never_defaults_to_one():
    assert cf.tenant_dial_code({'default_country_code':'61'})=='61'
    assert cf.tenant_dial_code({'default_country_code':'','timezone':'Pacific/Auckland'})=='64'
    assert cf.tenant_dial_code({'timezone':'Australia/Sydney'})=='61'
    assert cf.tenant_dial_code({'default_country_code':'','timezone':'America/Chicago'})==''
    assert cf.country_for_e164('+12125550100')=='US' and cf.country_for_e164('+6492431347')=='NZ'


def test_owner_connection_is_scoped_and_does_not_claim_live_without_inbound_call(monkeypatch):
    pool=FakePool(connection=connection())
    use(monkeypatch,pool)
    result=asyncio.run(m.mobile_connection(owner()))
    assert result['status']=='ready_to_forward' and result['last_call'] is None
    assert result['destination']==NZ_DID and result['destination_display']=='092431347'
    assert result['country']=='NZ' and result['carrier']=='spark_nz' and result['country_mismatch'] is False
    assert codes(result['steps'])==['*61*092431347*11#','*67*092431347*11#']
    assert {c['code'] for c in result['countries']}>={'NZ','AU','GB','US','ZZ'} and result['device_hints']['iphone']['tap_to_dial'] is False
    assert any(c['id']=='spark_nz' for c in result['carriers']) and result['notify_phone']=='+64275550123'
    assert set(pool.args)=={'business-a'}


def test_first_forwarded_call_is_reported_as_call_received(monkeypatch):
    use(monkeypatch,FakePool(connection=connection(),call={'call_sid':'CA1','status':'completed','owner_message_queued':True}))
    result=asyncio.run(m.mobile_connection(owner()))
    assert result['status']=='call_received' and result['last_call']['call_sid']=='CA1'


def test_owner_connection_never_exposes_another_business_or_unapproved_route(monkeypatch):
    use(monkeypatch,FakePool())
    result=asyncio.run(m.mobile_connection(owner('business-b')))
    assert result['status']=='destination_needed' and result['destination'] is None
    assert result['steps']['set']==[] and result['countries']  # pickers still available before a number exists
    use(monkeypatch,FakePool(connection=connection()),authorized=False)
    result=asyncio.run(m.mobile_connection(owner('business-b')))
    assert result['status']=='authorization_needed' and result['destination'] is None and result['steps']['set']==[]
    use(monkeypatch,FakePool(connection=connection(designated_number=NZ_DID)))
    assert asyncio.run(m.mobile_connection(owner()))['status']=='destination_needed'


def test_country_mismatch_and_loop_are_warnings_in_the_owner_response(monkeypatch):
    pool=FakePool(tenant={'pref_country':'AU','pref_carrier':'telstra_au','notify_phone':'092431347'},connection=connection(carrier='other'))
    use(monkeypatch,pool)
    result=asyncio.run(m.mobile_connection(owner()))
    assert result['status']=='ready_to_forward' and result['country']=='AU' and result['country_mismatch'] is True
    assert codes(result['steps'])[0].startswith('*61*+649')
    use(monkeypatch,FakePool(tenant={'notify_phone':'+64 9 243 1347'},connection=connection()))
    assert asyncio.run(m.mobile_connection(owner()))['destination_is_notify_phone'] is True
    use(monkeypatch,FakePool(tenant={'notify_phone':'+64275550123'},connection=connection()))
    assert asyncio.run(m.mobile_connection(owner()))['destination_is_notify_phone'] is False


def test_owner_can_update_country_carrier_and_answer_mode_but_not_the_destination(monkeypatch):
    pool=FakePool(connection=connection(carrier='other'),tenant={'pref_country':'AU','pref_carrier':'telstra_au','pref_answer_mode':'all_calls'})
    use(monkeypatch,pool)
    result=asyncio.run(m.save_mobile_preferences(m.MobilePreferences(country='au',carrier='telstra_au',answer_mode='all_calls'),owner()))
    sql,args=pool.executed[0]
    assert 'call_forwarding_preferences' in sql and args==('business-a','AU','telstra_au','all_calls')
    assert any('managed_phone_setups' in q and a[1]=='all_calls' for q,a in pool.executed)
    assert result['status']=='ready_to_forward'
    for attempt in ({'destination':'+6499999999'},{'destination_country':'NZ'},{'answer_mode':'sometimes'}):
        with pytest.raises(ValidationError):m.MobilePreferences(**attempt)
    # A made-up carrier is stored as 'other'.
    asyncio.run(m.save_mobile_preferences(m.MobilePreferences(carrier='made_up'),owner()))
    assert pool.executed[-1][1][2]=='other'


def test_owner_cannot_bind_a_forwarding_number_or_activate_a_business(monkeypatch):
    from app.main import app
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'admin_token','fixture-admin-only')
    async def auth():return {'tenant_id':'business-a','role':'owner'}
    app.dependency_overrides[m.owner_auth.current_user]=auth
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as client:
            admin=await client.put('/admin/tenants/business-b/mobile-connection',json={'destination':'+6495550100'})
            smuggled=await client.put('/owner/mobile-connection',json={'destination':'+6495550100'})
            return admin.status_code,smuggled.status_code
    try:
        assert asyncio.run(scenario())==(401,422)
    finally:app.dependency_overrides.clear()


def bind(monkeypatch,tenant,body,enabled=True):
    async def get_by_slug(slug):return {'id':'t1','slug':slug,**tenant}
    class Conn(FakePool):
        async def fetchrow(self,sql,*a):return {'connection':'mobile_forwarding','designated_number':'+64275550123'}
        async def fetchval(self,sql,*a):return 1 if enabled else None
    conn=Conn()
    monkeypatch.setattr(m.tenants,'get_by_slug',get_by_slug)
    monkeypatch.setattr(m.db,'pool',lambda:conn)
    return asyncio.run(m.bind_mobile_connection('business-a',m.MobileConnection(**body))),conn


def test_admin_bind_in_another_country_warns_but_still_binds(monkeypatch):
    result,conn=bind(monkeypatch,{'default_country_code':'64'},{'destination':'+61291234567','carrier':'telstra_au'})
    assert result['status']=='ready_to_forward' and result['destination_country']=='AU' and 'not in the business' in result['warning']
    assert any('INSERT INTO mobile_forwarding_connections' in q and a[3]=='AU' for q,a in conn.executed)


def test_admin_bind_in_the_tenants_own_country_has_no_warning_and_old_carriers_still_work(monkeypatch):
    result,conn=bind(monkeypatch,{'default_country_code':'','timezone':'Pacific/Auckland'},{'destination':NZ_DID,'carrier':'spark_nz'})
    assert 'warning' not in result and result['carrier']=='spark_nz' and result['destination_country']=='NZ'
    result,_=bind(monkeypatch,{'default_country_code':'64'},{'destination':NZ_DID})
    assert result['carrier']=='other'
    result,_=bind(monkeypatch,{'default_country_code':'64'},{'destination':NZ_DID,'carrier':'nonsense'})
    assert result['carrier']=='other'


def test_admin_bind_still_refuses_the_public_number_and_unconnected_numbers(monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        bind(monkeypatch,{'default_country_code':'64'},{'destination':'+64275550123'})
    assert e.value.status_code==409
    with pytest.raises(HTTPException) as e:
        bind(monkeypatch,{'default_country_code':'64'},{'destination':NZ_DID},enabled=False)
    assert e.value.status_code==409
