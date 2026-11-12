"""Direct Grok speech-to-speech over customer-owned carrier/PBX SIP routing.

Official xAI SIP webhooks are verified before call lookup. No carrier change,
Twilio speech synthesis or local audio driver is required. Audio is not stored.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid

import httpx
import websockets
from websockets.exceptions import ConnectionClosedOK
from fastapi import APIRouter, HTTPException, Request

from . import channel_authorization, convo, db, enquiries, events, tenants, voice, voice_records
from . import missed_calls
from .config import get_settings
from .rag import build_system_prompt
from .tools import run_tool

router=APIRouter(prefix="/api/v1/phone/xai")
log=logging.getLogger("concierge.sip")


def valid_signature(secret, body, headers, now=None):
    try:
        if not secret.startswith("whsec_"):
            return False
        key=base64.b64decode(secret[6:],validate=True)
        stamp=headers.get("webhook-timestamp","")
        ident=headers.get("webhook-id","")
        if (len(key)<24 or not ident or len(ident)>200 or
                abs((time.time() if now is None else now)-int(stamp))>300):
            return False
        expected=base64.b64encode(hmac.new(key,(ident+"."+stamp+".").encode()+body,hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(part[3:],expected)
                   for part in headers.get("webhook-signature","").split() if part.startswith("v1,"))
    except (ValueError,TypeError):
        return False


def header_number(headers,name):
    values=[v.get("value","") for v in headers if isinstance(v,dict) and str(v.get("name","")).lower()==name.lower()]
    if len(values)!=1 or not isinstance(values[0],str):
        return ""
    found=re.findall(r"\+[1-9]\d{6,14}(?!\d)",values[0])
    return found[0] if len(found)==1 else ""


def connection_config(ident):
    try:
        ident=str(uuid.UUID(str(ident)))
        values=json.loads(get_settings().xai_sip_connections or "{}")
        item=values.get(ident,{})
        if not item.get("enabled") or not item.get("tenant") or not item.get("number") or not item.get("signing_secret"):
            raise ValueError()
        return item
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(503,"This telephone connection is not enabled") from None


def configured_for_tenant(tenant,numbers):
    if not get_settings().phone_receptionist_enabled or not get_settings().xai_api_key or get_settings().phone_voice_provider!='grok':
        return False
    try:
        configs=json.loads(get_settings().xai_sip_connections or '{}')
        for ident in configs:
            try:
                item=connection_config(ident)
            except HTTPException:
                continue
            if item['tenant']==tenant.get('slug') and any(n['enabled'] and n['e164']==item['number'] for n in numbers):
                return True
    except (ValueError,TypeError,KeyError):
        pass
    return False


async def call_control(call_id,action):
    # Call IDs are UUIDs verified before any provider URL is constructed.
    call_id=str(uuid.UUID(call_id))
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        r=await client.post("https://api.x.ai/v1/realtime/calls/"+call_id+"/"+action,
            headers={"Authorization":"Bearer "+get_settings().xai_api_key})
    return r.status_code in (200,204,404)


async def serve_call(call_id,tenant,caller):
    session_id="sip:"+call_id
    status="completed";caller_turns=[];conversation=None;record_session=None
    try:
        conversation=await convo.get_or_create(tenant,session_id,"phone",None,None)
        context={"conversation_id":conversation,"session_id":session_id,"channel":"phone","sender_phone":caller}
        await enquiries.capture(tenant,"phone",session_id,"Inbound telephone enquiry",
                                conversation_id=conversation,phone=caller)
        # A telephone call serves a voice session exactly as the website widget does, so the caller
        # can be sent a copy of the conversation afterwards. Without this the copy tool has no
        # session to attach the request to and refuses, which is why phone callers could never be
        # sent a summary. `record=False`: Concierge does not record calls unless asked.
        capability=await voice_records.start(tenant,session_id,channel="phone")
        record_session=await voice_records.authenticate(capability["id"],capability["token"])
        context["voice_session"]=record_session
        session=voice.build_session(tenant,copy_delivery=True)
        session["instructions"]=build_system_prompt(tenant,None,channel="phone")+(
            "\nYou are the business's automated phone receptionist using Grok voice. "
            "Greet the caller and disclose that this call is transcribed to handle the enquiry. "
            "Do not claim to be human. Audio is not recorded by Concierge. "
            "Use the business information and tools; never invent facts or say a text was sent without a confirmed result. "
            "When the caller is finished, say goodbye then call end_call. Do not end a call with an open question."
        )
        session["tools"].append({"type":"function","name":"end_call","description":"End the call after the caller has finished and you have said goodbye.","parameters":{"type":"object","properties":{},"additionalProperties":False}})
        # SIP handles codecs and audio transport. Keep native Grok speech, not
        # an intermediate carrier TTS voice or a microphone on the operator Mac.
        session["audio"]={"input":{"transcription":{"model":"grok-transcribe"}}}
        async with asyncio.timeout(600):
            async with websockets.connect("wss://api.x.ai/v1/realtime?call_id="+call_id,
                    additional_headers={"Authorization":"Bearer "+get_settings().xai_api_key},open_timeout=15) as ws:
                await db.pool().execute("UPDATE phone_calls SET status='in_progress' WHERE call_sid=$1",session_id)
                await ws.send(json.dumps({"type":"session.update","session":session}))
                pending=[];seen_tools=set();caller_spoke=False;ending_deadline=None;ending_tools=[];auth_checked=0
                while True:
                    if time.monotonic()-auth_checked>=5:
                        if not await channel_authorization.is_authorized(tenant["id"],"telephone"):
                            status="authorization_revoked";break
                        auth_checked=time.monotonic()
                    try:
                        timeout=15 if ending_deadline is None else max(.01,min(15,ending_deadline-time.monotonic()))
                        message=await asyncio.wait_for(ws.recv(),timeout=timeout)
                    except asyncio.TimeoutError:
                        if ending_deadline is not None and time.monotonic()>=ending_deadline:
                            break
                        continue
                    event=json.loads(message);kind=event.get("type")
                    if kind=="session.updated":
                        await ws.send(json.dumps({"type":"response.create"}))
                    elif kind=="error":
                        raise RuntimeError("Grok telephone session rejected an event")
                    elif kind=="input_audio_buffer.speech_started":
                        caller_spoke=True
                        if ending_deadline is not None:
                            ending_deadline=None
                            for tool_id in ending_tools:
                                await ws.send(json.dumps({"type":"conversation.item.create","item":{
                                    "type":"function_call_output","call_id":tool_id,"output":json.dumps({"ok":False,"note":"Caller resumed speaking; continue the conversation."})}}))
                            ending_tools=[]
                    elif kind in ("conversation.item.input_audio_transcription.completed","response.output_audio_transcript.done"):
                        text=event.get("transcript","")
                        if isinstance(text,str) and text:
                            await convo.save_message(conversation,"user" if kind.startswith("conversation") else "assistant",text[:10000])
                            if kind.startswith('conversation'):
                                caller_turns.append(text[:4000]);caller_turns=caller_turns[-40:]
                    elif kind=="response.function_call_arguments.done":
                        tool_id=event.get("call_id","")
                        if not isinstance(tool_id,str) or not tool_id or len(tool_id)>200 or tool_id in seen_tools or len(seen_tools)>=40:
                            continue
                        seen_tools.add(tool_id)
                        if event.get("name")=="end_call" and caller_spoke:
                            pending.append((tool_id,{"ok":True,"ending":True}))
                        else:
                            try:
                                arguments=json.loads(event.get("arguments","{}"))
                            except (ValueError,TypeError):
                                arguments={}
                            result=await run_tool(tenant,event.get("name",""),arguments,context)
                            pending.append((tool_id,result))
                    elif kind=="response.done" and pending:
                        results,pending=pending,[]
                        if any(result.get("ending") for _,result in results):
                            # Generation completion is not proof the farewell
                            # finished playing. Leave time for audio and barge-in.
                            ending_deadline=time.monotonic()+3
                            ending_tools=[tool_id for tool_id,result in results if result.get("ending")]
                            continue
                        for tool_id,result in results:
                            await ws.send(json.dumps({"type":"conversation.item.create","item":{
                                "type":"function_call_output","call_id":tool_id,"output":json.dumps(result,default=str)}}))
                        await ws.send(json.dumps({"type":"response.create"}))
    except ConnectionClosedOK:
        pass
    except Exception as error:
        status="failed"
        log.warning("Grok telephone session ended: %s",type(error).__name__)
    finally:
        try:
            if not await call_control(call_id,"hangup"):
                status="hangup_unconfirmed"
                log.warning("Telephone hangup was not confirmed by provider")
        except Exception:
            status="hangup_unconfirmed"
            log.warning("Telephone hangup needs provider reconciliation")
        await db.pool().execute("UPDATE phone_calls SET status=$2,ended_at=now() WHERE call_sid=$1",session_id,status)
        # Missed-call text-back (competitor-gap item A). A call that ends without a conversation
        # is a lost job; this gives the caller one reply and the owner a lead. Never let it change
        # the recorded outcome of the call.
        try:
            await missed_calls.evaluate_call_sid(session_id)
        except Exception:
            log.warning("Missed-call recovery needs reconciliation for %s",session_id)
        if caller_turns and conversation:
            await db.pool().execute(
                "UPDATE leads SET message=$3,updated_at=now() WHERE tenant_id=$1 AND conversation_id=$2 "
                "AND message='Inbound telephone enquiry'",tenant['id'],conversation,'\n'.join(caller_turns)[-1000:])
        # Deliver the copy the caller asked for. The request was recorded on the voice session while
        # the call was live; this is the only moment it can be flushed, because a session that is
        # never finalized also never sends, and the request would be silently dropped. Finalizing
        # and reading the request in ONE statement keeps the same guarantee Asterisk relies on: a
        # request arriving after this point cannot be half-honoured. Failures are logged, never
        # raised -- a failed courtesy copy must not change the recorded outcome of the call.
        if record_session:
            try:
                request=await db.pool().fetchval(
                    "UPDATE voice_sessions SET finalized_at=now() WHERE id=$1 AND finalized_at IS NULL "
                    "RETURNING delivery_request",record_session["id"])
                if request:
                    await voice_records.complete_delivery(record_session,tenant,request,{"ok":True})
            except Exception:
                log.warning("Telephone copy delivery needs reconciliation")


@router.post("/{connection_id}")
async def incoming(connection_id: uuid.UUID,request: Request):
    config=connection_config(connection_id)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>65536:
            raise HTTPException(413,"Telephone event too large")
    body=bytes(body)
    if not valid_signature(config["signing_secret"],body,request.headers):
        raise HTTPException(403,"Invalid telephone event signature")
    try:
        event=json.loads(body)
        if event.get("type")!="realtime.call.incoming":
            return {"ok":True}
        data=event["data"];call_id=str(uuid.UUID(data["call_id"]))
        number=header_number(data.get("sip_headers",[]),"To")
        caller=header_number(data.get("sip_headers",[]),"From")
    except (ValueError,TypeError,KeyError,AttributeError):
        raise HTTPException(400,"Invalid telephone event") from None
    tenant=await tenants.get_by_slug(config["tenant"])
    if (not get_settings().phone_receptionist_enabled or number!=config["number"] or not tenant or not tenant.get("phone_enabled")
            or not get_settings().xai_api_key
            or get_settings().phone_voice_provider!='grok'
            or not await channel_authorization.is_authorized(tenant["id"],"telephone")):
        raise HTTPException(403,"Telephone connection is not authorized")
    async with db.pool().acquire() as c:
        async with c.transaction():
            await c.execute("SELECT id FROM tenants WHERE id=$1 FOR UPDATE",tenant["id"])
            enabled=await c.fetchval("SELECT 1 FROM phone_numbers WHERE tenant_id=$1 AND e164=$2 AND enabled",tenant["id"],number)
            if not enabled:
                raise HTTPException(403,"Telephone number is not activated")
            previous=await c.fetchval("SELECT tenant_id FROM phone_calls WHERE call_sid=$1","sip:"+call_id)
            if previous:
                if previous!=tenant["id"]:
                    raise HTTPException(403,"Call belongs to another business")
                return {"ok":True,"duplicate":True}
            used=await c.fetchval("SELECT count(*) FROM phone_calls WHERE tenant_id=$1 AND started_at>=now()-interval '1 day'",tenant["id"])
            if used>=tenant["phone_daily_limit"]:
                raise HTTPException(429,"Daily telephone limit reached")
            await c.execute("INSERT INTO phone_calls(call_sid,tenant_id,session_id,from_number,to_number) VALUES($1,$2,$1,$3,$4)",
                            "sip:"+call_id,tenant["id"],caller,number)
    events.spawn(serve_call(call_id,tenant,caller))
    return {"ok":True}
