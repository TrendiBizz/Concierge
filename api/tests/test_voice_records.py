import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from app import voice_records as r


@pytest.mark.parametrize('mime,body',[('audio/webm',b'\x1aE\xdf\xa3'+b'x'*20),('audio/ogg',b'OggS'+b'x'*20),('audio/mp4',b'\0\0\0\x18ftyp'+b'x'*20)])
def test_audio_container_matches_type(mime,body):
    assert r.audio_type(mime+';codecs=opus',body)==mime
    with pytest.raises(HTTPException):r.audio_type(mime,b'<html>not audio at all</html>')


def test_recording_requires_business_and_caller_permission(monkeypatch):
    monkeypatch.setattr(r,'get_settings',lambda:SimpleNamespace(voice_recording_enabled=True))
    monkeypatch.setattr(r.channel_authorization,'is_authorized',AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as err:asyncio.run(r.start({'id':uuid.uuid4()},'session123',record=True))
    assert err.value.status_code==403
    monkeypatch.setattr(r.channel_authorization,'is_authorized',AsyncMock(return_value=True))
    with pytest.raises(HTTPException):asyncio.run(r.store_audio({'recording_consent':False},b'OggS'+b'x'*20,'audio/ogg'))


def test_recording_read_and_share_are_tenant_scoped(monkeypatch):
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value=None))
    monkeypatch.setattr(r.db,'pool',lambda:pool)
    business=uuid.uuid4();session=uuid.uuid4()
    with pytest.raises(HTTPException) as err:asyncio.run(r.audio_for_owner(business,session))
    assert err.value.status_code==404
    assert pool.fetchrow.await_args.args[1:]==(business,session)
    assert 'created_at' in pool.fetchrow.await_args.args[0]


def test_share_authentication_checks_expiry_and_never_stores_plain_token(monkeypatch):
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value=None));monkeypatch.setattr(r.db,'pool',lambda:pool)
    token='test-only-token-which-is-long-enough-for-check'
    with pytest.raises(HTTPException):asyncio.run(r.shared_audio(token))
    assert pool.fetchrow.await_args.args[1]==r.digest(token)
    assert 'expires_at>now()' in pool.fetchrow.await_args.args[0]


@pytest.mark.parametrize('recipient,consent',[('+64215550111',True),('+64215550100',False)])
def test_delivery_cannot_send_to_another_contact_or_without_consent(monkeypatch,recipient,consent):
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value={'phone':'+64215550100','email':'a@example.com','consent_contact':consent}))
    monkeypatch.setattr(r.db,'pool',lambda:pool)
    with pytest.raises(HTTPException) as err:
        asyncio.run(r.deliver({'id':uuid.uuid4()},uuid.uuid4(),recipient=recipient,channel='sms',content='text',request_id=uuid.uuid4()))
    assert err.value.status_code==403


@pytest.mark.parametrize('confirmed,recorded,content', [(False, True, 'text'), (True, False, 'recording')])
def test_copy_request_requires_readback_and_recording_opt_in(monkeypatch, confirmed, recorded, content):
    with pytest.raises(HTTPException) as err:
        asyncio.run(r.request_delivery({'recording_consent': recorded}, {}, channel='sms', content=content, confirmed=confirmed))
    assert err.value.status_code == 409


def test_copy_request_uses_saved_consented_recipient_and_waits_for_completion(monkeypatch):
    tenant={'id':uuid.uuid4()};session={'id':uuid.uuid4(),'conversation_id':uuid.uuid4(),'recording_consent':True}
    pool=SimpleNamespace(fetchrow=AsyncMock(return_value={'phone':'+64215550100','email':'','consent_contact':True}),fetchval=AsyncMock(return_value=session['id']))
    monkeypatch.setattr(r.db,'pool',lambda:pool)
    monkeypatch.setattr(r.channel_authorization,'is_authorized',AsyncMock(return_value=True))
    send=AsyncMock();monkeypatch.setattr(r.outbox,'enqueue',send)
    result=asyncio.run(r.request_delivery(session,tenant,channel='sms',content='recording',confirmed=True))
    assert result['status']=='requested' and result['recipient']=='+64215550100'
    assert 'finalized_at IS NULL' in pool.fetchval.await_args.args[0]
    assert '+64215550100' in pool.fetchval.await_args.args[2]
    send.assert_not_awaited()
    pool.fetchrow.return_value['consent_contact']=False
    with pytest.raises(HTTPException):asyncio.run(r.request_delivery(session,tenant,channel='sms',content='text',confirmed=True))


def test_copy_tool_requires_verified_session_and_is_not_offered_on_sip():
    from app import tools,voice
    result=asyncio.run(tools.run_tool({},'request_conversation_copy',{'channel':'sms','content':'text','confirmed':True},{}))
    assert result['ok'] is False
    tenant={'name':'Fixture','voice_enabled':True}
    assert 'request_conversation_copy' not in {t['name'] for t in voice.build_session(tenant)['tools']}
    assert 'request_conversation_copy' in {t['name'] for t in voice.build_session(tenant,website=True)['tools']}


@pytest.mark.parametrize('mismatch',['tenant','conversation'])
def test_voice_tool_capability_cannot_be_used_for_a_different_conversation(monkeypatch,mismatch):
    from app import main
    tenant={'id':uuid.uuid4()};conversation=uuid.uuid4()
    monkeypatch.setattr(main,'_rate_limit',lambda *args:None)
    monkeypatch.setattr(main,'_tenant_for',AsyncMock(return_value=tenant))
    monkeypatch.setattr(main.convo,'get_or_create',AsyncMock(return_value=conversation))
    session={'tenant_id':tenant['id'],'conversation_id':conversation}
    session['tenant_id' if mismatch=='tenant' else 'conversation_id']=uuid.uuid4()
    monkeypatch.setattr(r,'authenticate',AsyncMock(return_value=session))
    handler=AsyncMock();monkeypatch.setattr(main,'run_tool',handler)
    req=main.ToolRequest(key='fixture',session_id='fixture-123',voice_session_id=uuid.uuid4(),voice_session_token='test-only')
    with pytest.raises(HTTPException) as err:asyncio.run(main.tool_endpoint('request_conversation_copy',req,None))
    assert err.value.status_code==403
    handler.assert_not_awaited()
