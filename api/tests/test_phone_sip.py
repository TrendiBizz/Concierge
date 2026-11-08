import asyncio
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from app import phone_sip


def signed(body=b'{"type":"test"}',stamp='1000'):
    secret='whsec_'+base64.b64encode(b'k'*32).decode()
    expected=base64.b64encode(hmac.new(b'k'*32,b'evt.'+stamp.encode()+b'.'+body,hashlib.sha256).digest()).decode()
    return secret,body,{'webhook-id':'evt','webhook-timestamp':stamp,'webhook-signature':'v1,'+expected}


def test_sip_signature_requires_original_body_fresh_timestamp_and_secret():
    secret,body,headers=signed()
    assert phone_sip.valid_signature(secret,body,headers,now=1000)
    assert not phone_sip.valid_signature(secret,body+b' ',headers,now=1000)
    assert not phone_sip.valid_signature(secret,body,headers,now=1400)
    assert not phone_sip.valid_signature('whsec_invalid',body,headers,now=1000)
    assert not phone_sip.valid_signature(secret,body,{**headers,'webhook-id':'other'},now=1000)


@pytest.mark.parametrize('values,expected',[
    ([{'name':'To','value':'+6495550100'}],'+6495550100'),
    ([{'name':'to','value':'<sip:+6495550100@sip.voice.x.ai;transport=tls>'}],'+6495550100'),
    ([{'name':'To','value':'+6495550100'},{'name':'To','value':'+6495550101'}],''),
    ([{'name':'To','value':'+6495550100 +6495550101'}],''),
    ([{'name':'To','value':'anonymous'}],''),
])
def test_sip_number_parsing_is_unambiguous(values,expected):
    assert phone_sip.header_number(values,'To')==expected


class FakeSocket:
    def __init__(self,events):self.events=list(events);self.sent=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def send(self,value):self.sent.append(json.loads(value))
    async def recv(self):
        if self.events:return json.dumps(self.events.pop(0))
        await asyncio.sleep(3600)


def setup_session(monkeypatch,events):
    socket=FakeSocket(events)
    monkeypatch.setattr(phone_sip.websockets,'connect',lambda *args,**kwargs:socket)
    monkeypatch.setattr(phone_sip,'get_settings',lambda:SimpleNamespace(xai_api_key='test-only'))
    monkeypatch.setattr(phone_sip.voice,'build_session',lambda tenant:{'voice':'ara','tools':[]})
    monkeypatch.setattr(phone_sip,'build_system_prompt',lambda *args,**kwargs:'Verified business facts')
    monkeypatch.setattr(phone_sip.convo,'get_or_create',AsyncMock(return_value=uuid.uuid4()))
    save=AsyncMock();monkeypatch.setattr(phone_sip.convo,'save_message',save)
    monkeypatch.setattr(phone_sip.enquiries,'capture',AsyncMock())
    monkeypatch.setattr(phone_sip.channel_authorization,'is_authorized',AsyncMock(return_value=True))
    pool=SimpleNamespace(execute=AsyncMock());monkeypatch.setattr(phone_sip.db,'pool',lambda:pool)
    hangup=AsyncMock(return_value=True);monkeypatch.setattr(phone_sip,'call_control',hangup)
    return socket,save,hangup,pool


def test_grok_sip_uses_native_voice_and_finishes_transcribed_call_after_farewell(monkeypatch):
    events=[{'type':'session.updated'},{'type':'input_audio_buffer.speech_started'},
        {'type':'conversation.item.input_audio_transcription.completed','transcript':'Goodbye'},
        {'type':'response.output_audio_transcript.done','transcript':'Goodbye'},
        {'type':'response.function_call_arguments.done','name':'end_call','call_id':'tool-1','arguments':'{}'},
        {'type':'response.done'}]
    socket,save,hangup,pool=setup_session(monkeypatch,events)
    asyncio.run(phone_sip.serve_call(str(uuid.uuid4()),{'id':uuid.uuid4()},'+64215550100'))
    session=socket.sent[0]['session']
    assert session['voice']=='ara' and session['audio']['input']['transcription']['model']=='grok-transcribe'
    assert 'transcribed' in session['instructions'] and 'Audio is not recorded' in session['instructions']
    assert [c.args[1] for c in save.await_args_list]==['user','assistant']
    finishes=[c for c in pool.execute.await_args_list if c.args[0].startswith('UPDATE phone_calls SET status=$2')]
    assert hangup.await_count==1 and finishes[-1].args[-1]=='completed'


def test_grok_default_cannot_silently_use_carrier_text_to_speech(monkeypatch):
    from app import phone_relay
    settings=SimpleNamespace(phone_voice_provider='grok',phone_receptionist_enabled=True,
                             twilio_auth_token='test-only',public_base_url='https://example.invalid')
    monkeypatch.setattr(phone_relay,'get_settings',lambda:settings)
    assert not phone_relay.configured()


def test_caller_barge_in_cancels_pending_hangup(monkeypatch):
    events=[{'type':'session.updated'},{'type':'input_audio_buffer.speech_started'},
        {'type':'response.function_call_arguments.done','name':'end_call','call_id':'tool-1','arguments':'{}'},
        {'type':'response.done'},{'type':'input_audio_buffer.speech_started'},
        {'type':'conversation.item.input_audio_transcription.completed','transcript':'One more question'},
        {'type':'error'}]
    socket,save,hangup,_=setup_session(monkeypatch,events)
    asyncio.run(phone_sip.serve_call(str(uuid.uuid4()),{'id':uuid.uuid4()},'+64215550100'))
    outputs=[v['item'] for v in socket.sent if v['type']=='conversation.item.create']
    assert len(outputs)==1 and 'Caller resumed' in outputs[0]['output']
    assert save.await_args.args[-1]=='One more question' and hangup.await_count==1


def test_replayed_function_event_does_not_repeat_business_action(monkeypatch):
    tool={'type':'response.function_call_arguments.done','name':'capture_lead','call_id':'same-tool','arguments':'{}'}
    socket,_,_,_=setup_session(monkeypatch,[{'type':'session.updated'},tool,tool,{'type':'response.done'},{'type':'error'}])
    run=AsyncMock(return_value={'ok':True});monkeypatch.setattr(phone_sip,'run_tool',run)
    asyncio.run(phone_sip.serve_call(str(uuid.uuid4()),{'id':uuid.uuid4()},'+64215550100'))
    assert run.await_count==1
    assert len([x for x in socket.sent if x['type']=='conversation.item.create'])==1
