import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from app import managed_phone as m


def test_setup_rejects_injected_destinations_and_provider_secrets():
    for extra in ({'designated_number':'sip:attacker@invalid'}, {'sip_password':'secret'}, {'answer_mode':'invalid'}):
        with pytest.raises(ValidationError):
            m.PhoneSetup(**{'designated_number':'+64278817368','owner_number':'+64278817368',**extra})


def test_carrier_audio_routes_directly_to_grok_with_escaped_credentials():
    root=ElementTree.fromstring(m.sip_twiml({'number':'+6495550100','sip_username':'u"<&','sip_password':'p"<&'}))
    sip=root.find('Dial/Sip')
    assert sip.text=='sip:+6495550100@sip.voice.x.ai;transport=tls'
    assert sip.attrib['password']=='p"<&'
    assert root.find('Dial').attrib['timeLimit']=='600'
    assert root.find('.//ConversationRelay') is None


def request(body):
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    return Request({'type':'http','method':'POST','path':'/api/v1/phone/managed/twilio','query_string':b'','headers':[]},receive)


def setup(monkeypatch):
    settings=SimpleNamespace(phone_receptionist_enabled=True,phone_voice_provider='grok',twilio_account_sid='ACtest',xai_sip_connections='{"route":{}}')
    monkeypatch.setattr(m,'get_settings',lambda:settings)
    monkeypatch.setattr(m.phone_relay,'external_url',lambda path:'https://example.com'+path)
    monkeypatch.setattr(m.phone_relay.sms,'validate_signature',lambda *a:True)
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value={'id':'tenant-a','slug':'business-a'}))
    monkeypatch.setattr(m.db,'pool',lambda:pool)
    monkeypatch.setattr(m.channel_authorization,'is_authorized',AsyncMock(return_value=True))
    monkeypatch.setattr(m.phone_sip,'connection_config',lambda ident:{'tenant':'business-a','number':'+6495550100','sip_username':'u','sip_password':'p','carrier_account_sid':'ACtest','carrier_auth_token':'token'})
    return settings,pool


BODY=b'AccountSid=ACtest&CallSid=CA'+b'a'*32+b'&To=%2B6495550100'


def test_signed_inbound_routes_only_activated_tenant_number(monkeypatch):
    settings,pool=setup(monkeypatch)
    result=asyncio.run(m.carrier_incoming("route", request(BODY)))
    assert result.status_code==200 and b'sip:+6495550100@sip.voice.x.ai' in result.body
    assert pool.fetchrow.await_args.args[1]=='+6495550100'
    monkeypatch.setattr(m.phone_sip,'connection_config',lambda ident:{'tenant':'business-b','number':'+6495550100','carrier_account_sid':'ACtest','carrier_auth_token':'token'})
    with pytest.raises(HTTPException) as err:asyncio.run(m.carrier_incoming("route", request(BODY)))
    assert err.value.status_code==403


@pytest.mark.parametrize('case',['disabled','signature','duplicate','account','authorization'])
def test_carrier_rejects_unauthorized_routes(monkeypatch,case):
    settings,pool=setup(monkeypatch);body=BODY
    if case=='disabled':settings.phone_receptionist_enabled=False
    if case=='signature':monkeypatch.setattr(m.phone_relay.sms,'validate_signature',lambda *a:False)
    if case=='duplicate':body+=b'&To=%2B6495550101'
    if case=='account':body=body.replace(b'ACtest',b'ACother')
    if case=='authorization':monkeypatch.setattr(m.channel_authorization,'is_authorized',AsyncMock(return_value=False))
    with pytest.raises(HTTPException):asyncio.run(m.carrier_incoming("route", request(body)))


@pytest.mark.parametrize('role,code',[('viewer',403),('editor',403),('owner',200)])
def test_owner_setup_is_tenant_scoped_and_cannot_activate_or_purchase(monkeypatch,role,code):
    import httpx
    from app.main import app
    from app import owner_auth
    identity={'tenant_id':'business-a','role':role}
    async def auth():return identity
    app.dependency_overrides[owner_auth.current_user]=auth
    write=AsyncMock(return_value={'status':'requested'})
    monkeypatch.setattr(m,'save_setup',write)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://testserver') as client:
            return await client.put('/owner/phone-setup',json={'designated_number':'+64278817368','owner_number':'+64278817368','connection':'existing_sip'})
    try:
        result=asyncio.run(run())
        assert result.status_code==code
        if role=='owner':assert write.await_args.args[0]=='business-a'
        else:write.assert_not_awaited()
    finally:app.dependency_overrides.clear()


def test_new_service_purchase_is_not_a_setup_option():
    with pytest.raises(ValidationError):
        m.PhoneSetup(designated_number='+64278817368',owner_number='+64278817368',connection='new_number')
