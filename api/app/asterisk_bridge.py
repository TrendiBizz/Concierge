"""Private Asterisk AudioSocket → native Grok voice bridge.

One listener per provisioned business: the caller/model never chooses a tenant.
Run separately from HTTP workers: python -m app.asterisk_bridge.
AudioSocket is unencrypted: bind loopback or an isolated private container network.
"""
import asyncio
import base64
from dataclasses import dataclass
import ipaddress
import json
import logging
import os
import re
import secrets
import struct
import uuid

import websockets

from . import (call_control, channel_authorization, convo, db, enquiries, events, tenants, voice,
               voice_records)
from .config import get_settings
from .rag import build_system_prompt
from .tools import run_tool
from .telephone_recording import TelephoneRecording

log = logging.getLogger('concierge.asterisk')
FRAME_BYTES = 320  # 20ms PCM16 LE mono at 8kHz, native AudioSocket application format
MAX_SECONDS = 600
# Silent monitoring changes what a caller must be told, so the greeting discloses it *when the
# capability exists* -- not speculatively, and not only in a policy document.
LIVE_LISTEN_DISCLOSURE = (
    ' This line is answered by an automated assistant, and a member of our team may listen to the '
    'call while it happens or join it. Say so in your greeting, in your own words.')
# A `response.cancel` that races the end of a response comes back as
# "Cancellation failed: no active response found". That is not a dead call -- the
# barge-in already achieved what it wanted -- so one error event must never end a
# session. Only a session that keeps failing is treated as unusable.
MAX_ERRORS = 5
# These are not failures at all: xAI refuses a cancel that raced the end of the
# response, which happens whenever a caller correctly stops the assistant
# mid-sentence. Counting them ended a real 58-second call.
BENIGN_ERRORS = ('cancellation failed', 'no active response found')
# xAI's default VAD ends a turn after 200ms of quiet, which splits a caller
# dictating a phone number into three "turns" and makes the assistant interrupt.
SILENCE_DURATION_MS = 700
# Server VAD normally answers a caller turn on its own. If a cancelled or lost
# response leaves the caller in silence, ask the model once for that turn.
REPLY_NUDGE_SECONDS = 5.0


from .speech_text import clean_speech


# Say a number once. The test call of 2026-11-13 read the caller's number three times: the lead step,
# the text-copy step and the confirmation each told the model to read it back. A caller who then
# interrupts a read-back must not trigger a fresh one.
READBACK_RULES = (
    ' Say any phone number or email address back at most once on the whole call, in short groups, '
    'then carry on. After that, call it "that number" or "the same number" and never recite it again; '
    'these rules override any tool instruction to read back again. If the caller interrupts while you '
    'are reading something back, stop at once, treat what they said as the answer, and do not start '
    'the read-back over. If they correct a number, read only the corrected number, once. '
    'Never mention devices, queues, delivery systems or limits to the caller; say the team will follow up.')
SMS_OFFLINE_RULE = (
    ' Text messages cannot be sent right now. Do not offer a text copy or a recording link by SMS and '
    'do not promise any text. Offer a callback, or an email copy if the caller gives an email address.')


async def sms_copy_available(tenant_id) -> bool:
    """True when the business's SMS phone has checked in recently enough to send a text copy.

    A check that fails is treated as available, so a database hiccup never changes what callers hear.
    """
    try:
        return bool(await db.pool().fetchval(
            'SELECT 1 FROM sms_devices WHERE tenant_id=$1 AND enabled AND last_seen > now() - interval \'2 hours\' LIMIT 1',
            tenant_id))
    except Exception:  # noqa: BLE001
        log.exception('could not check the SMS device; assuming it is available')
        return True


QUICK_QUESTIONS = (
    'After the greeting, ask only what is needed to help, one short question at a time and under ten '
    'words each: what they need, their name, and the best number to call back (or an email if they '
    'prefer). Skip anything they have already told you and never ask for the same thing twice. '
    'Acknowledge in a word or two ("Got it."), never in a sentence. Do not offer a text copy, a '
    'recording link or any other extra unless the caller asks. If the caller asks to be contacted by '
    'email or text, save that as their contact preference with the number or address; that is a callback '
    'preference, not a copy of the conversation. If they do ask for a copy of the conversation, capture '
    'their contact, get one clear yes to the format and destination (say "the same number" if you already '
    'have it), then request_conversation_copy. Never claim a text was sent without a confirmed result. '
    'Once you have what they need, their name and how to reach them, say goodbye in one short sentence '
    'and call end_call. Do not end with an open question.')


def phone_instructions(name: str, *, recording_ok: bool, listen_in: bool, sms_ok: bool) -> str:
    """The telephone receptionist's instructions after the shared business prompt.

    The opening is two short sentences. "Recorded" is only ever said when recording will really happen
    (the business authorised it and the platform has it switched on); otherwise the notice says
    "transcribed", which is always true. Listen-in is added only while a human really can listen in.
    """
    business = (name or 'the business').replace('"', '').strip() or 'the business'
    listen = ' and a team member may listen in' if listen_in else ''
    verb = 'recorded' if recording_ok else 'transcribed'
    text = (
        "\nYou are this business's automated receptionist. Open the call with exactly this, warmly and with "
        f'nothing added: "Hello, I\'m the AI assistant for {business}. Our calls are {verb} for quality and '
        f'training purposes{listen}." ')
    if recording_ok:
        text += (
            'Right after saying it, call set_call_recording with enabled=true and confirmed=true: the caller '
            'has been told. If they object to recording or ask you to stop, call set_call_recording with '
            'enabled=false at once (it discards the audio), say "No problem" and carry on. ')
    else:
        text += 'Audio is not recorded on this line; never say or imply that it is. '
    return text + QUICK_QUESTIONS + READBACK_RULES + ('' if sms_ok else SMS_OFFLINE_RULE)


@dataclass(frozen=True)
class Route:
    tenant: str
    number: str
    port: int


def greeting_disclosure(media_control: bool) -> str:
    """The extra greeting sentence owed to callers when a human may listen in."""
    return LIVE_LISTEN_DISCLOSURE if media_control else ''


def routes_from_json(value):
    rows = json.loads(value)
    if not isinstance(rows, list) or not rows:
        raise ValueError('At least one explicit business route is required')
    routes = [Route(**r) for r in rows]
    if len({r.port for r in routes}) != len(routes):
        raise ValueError('Each business route needs a unique private port')
    if len({r.number for r in routes}) != len(routes):
        raise ValueError('Ambiguous forwarding destinations are forbidden')
    for r in routes:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', r.tenant):
            raise ValueError('Invalid business slug')
        if not re.fullmatch(r'\+[1-9]\d{6,14}', r.number) or not 1024 <= r.port <= 65535:
            raise ValueError('Invalid destination or listener port')
    return routes


async def packet(reader):
    kind, length = struct.unpack('!BH', await reader.readexactly(3))
    if length > 8192:
        raise ValueError('Oversized AudioSocket packet')
    return kind, await reader.readexactly(length)


async def send_packet(writer, kind, body=b''):
    writer.write(struct.pack('!BH', kind, len(body)) + body)
    await writer.drain()


class MediaBridge:
    """Bidirectional audio with bounded playback, pacing and barge-in flushing."""
    def __init__(self, reader, writer, ws, session, on_transcript, on_tool, recording=None,
                 reply_nudge=REPLY_NUDGE_SECONDS):
        self.recording = recording
        self.reader, self.writer, self.ws = reader, writer, ws
        self.session = session
        self.on_transcript, self.on_tool = on_transcript, on_tool
        self.playback = bytearray()
        self.ready = asyncio.Event()
        self.seen_transcripts, self.seen_tools = {}, set()
        self.ending = False
        self.speaking = False
        self.pending = []
        self.reply_nudge = reply_nudge
        # A response is only cancellable while `response.created` is current. VAD
        # can re-fire `speech_started` for an item that already finished, and the
        # server may have completed the response before the cancel lands, so track
        # both the live response and the caller turns that already ended.
        self.response_id = None
        self.ended_items = set()
        self.caller_speaking = False
        self.errors = 0
        self.benign_errors = 0
        # Only an audible reply is worth cancelling; cancelling one the caller
        # has not heard yet is what produces the benign error above.
        self.response_audible = False
        # A caller turn is owed a reply until the assistant actually produces
        # audio or speech for it. A cancelled or dropped response keeps the debt,
        # which is what the reply nudge in `watchdog` pays off.
        self.reply_pending = False
        self.reply_since = 0.0

    async def input(self):
        await asyncio.wait_for(self.ready.wait(), 15)
        reading = asyncio.create_task(packet(self.reader))
        try:
            while True:
                # Wait()/silent endpoints may send no frames. Grok still needs
                # real-time silence for VAD to finish the caller's turn. Shield
                # the packet read: cancelling readexactly can lose half a frame.
                done, _ = await asyncio.wait((reading,), timeout=.02)
                if done:
                    kind, body = reading.result()
                    if kind == 0:
                        return
                    if kind == 0x10:
                        if not body or len(body) % 2:
                            raise ValueError('Invalid PCM16 frame')
                    elif kind == 3 and len(body) == 1:
                        reading = asyncio.create_task(packet(self.reader))
                        continue
                    else:
                        raise ValueError('Unexpected AudioSocket frame')
                    reading = asyncio.create_task(packet(self.reader))
                else:
                    body = b'\0' * FRAME_BYTES
                if self.recording:
                    self.recording.append(body)
                await self.ws.send(json.dumps({'type': 'input_audio_buffer.append',
                                               'audio': base64.b64encode(body).decode()}))
        finally:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)

    async def output(self):
        idle_since = None
        while True:
            started = asyncio.get_running_loop().time()
            if self.playback:
                body = bytes(self.playback[:FRAME_BYTES])
                del self.playback[:FRAME_BYTES]
                played = body.ljust(FRAME_BYTES, b'\0')
                await send_packet(self.writer, 0x10, played)
                if self.response_id is not None:
                    self.response_audible = True
                if self.recording:
                    self.recording.append(played)
                idle_since = None
            elif self.ending and not self.speaking:
                idle_since = idle_since or started
                if started-idle_since >= .4:
                    return
            await asyncio.sleep(max(0, .02-(asyncio.get_running_loop().time()-started)))

    async def grok(self):
        await self.ws.send(json.dumps({'type': 'session.update', 'session': self.session}))
        async for message in self.ws:
            event = json.loads(message)
            kind = event.get('type')
            if kind == 'session.updated':
                if not self.ready.is_set():
                    self.ready.set()
                    await self.ws.send(json.dumps({'type': 'response.create'}))
            elif kind == 'error':
                # Log the server's words: the old code swallowed them and every
                # failed call ended up as an undiagnosable "RuntimeError".
                error = event.get('error') if isinstance(event.get('error'), dict) else {}
                detail = str(error.get('message') or event.get('message') or '')[:500]
                code = str(error.get('code') or error.get('type') or 'unknown')
                if any(marker in f'{code} {detail}'.lower() for marker in BENIGN_ERRORS):
                    self.benign_errors += 1
                    if self.benign_errors <= 3:
                        log.info('Benign Grok cancel race (%s): %s', self.benign_errors, detail)
                    if self.reply_pending:
                        self.reply_since = asyncio.get_running_loop().time()
                    continue
                self.errors += 1
                log.warning('Grok telephone session error %s/%s: %s', code, self.errors, detail)
                if self.errors >= MAX_ERRORS:
                    raise RuntimeError(f'Grok telephone session failed {self.errors} times: {code} {detail}')
                if self.reply_pending:
                    self.reply_since = asyncio.get_running_loop().time()
            elif kind == 'response.created':
                self.speaking = True
                self.response_id = event.get('response_id') or 'active'
                self.response_audible = False
            elif kind in ('response.canceled', 'response.cancelled'):
                self.speaking = False
                self.response_id = None
                # The cancelled reply never reached the caller; keep the debt so
                # the nudge can rebuild it if the caller stays silent.
                self.reply_pending = True
                self.reply_since = asyncio.get_running_loop().time()
            elif kind in ('response.output_audio.delta', 'response.audio.delta'):
                audio = base64.b64decode(event['delta'], validate=True)
                if len(audio) % 2 or len(self.playback)+len(audio) > 16000*30:
                    raise ValueError('Invalid or excessive Grok audio')
                self.playback.extend(audio)
                self.reply_pending = False
            elif kind == 'input_audio_buffer.speech_started':
                item = event.get('item_id')
                # The server can re-fire speech_started for a turn that already
                # stopped. Cancelling then races the next response and, worse,
                # leaves the caller with a half-played reply and no follow-up.
                if item and item in self.ended_items:
                    continue
                self.caller_speaking = True
                self.playback.clear()
                self.ending = False
                if self.response_id is not None and self.speaking and self.response_audible:
                    self.response_id = None
                    self.response_audible = False
                    self.reply_pending = True
                    self.reply_since = asyncio.get_running_loop().time()
                    await self.ws.send(json.dumps({'type': 'response.cancel'}))
            elif kind == 'input_audio_buffer.speech_stopped':
                self.caller_speaking = False
                if event.get('item_id'):
                    self.ended_items.add(event['item_id'])
            elif kind in ('conversation.item.input_audio_transcription.completed',
                          'response.output_audio_transcript.done', 'response.audio_transcript.done'):
                identity = (event.get('item_id') or event.get('response_id'),
                            'user' if kind.startswith('conversation') else 'assistant')
                text = event.get('transcript')
                if identity[1] == 'user':
                    self.reply_pending = True
                    self.reply_since = asyncio.get_running_loop().time()
                if isinstance(text, str) and text and (not identity[0] or self.seen_transcripts.get(identity) != text):
                    # Grok can emit successive cumulative COMPLETED events for
                    # the same item. Replace that turn, rather than freezing its
                    # first few words or appending duplicate partial messages.
                    self.seen_transcripts[identity] = text
                    if identity[1] == 'assistant':
                        self.reply_pending = False
                    await self.on_transcript(identity[1], text[:10000], identity[0])
            elif kind == 'response.function_call_arguments.done':
                ident = event.get('call_id')
                if not isinstance(ident, str) or not ident or len(ident)>200 or ident in self.seen_tools:
                    continue
                if len(self.seen_tools)>=40:
                    raise ValueError('Tool limit')
                self.seen_tools.add(ident)
                args = json.loads(event.get('arguments', '{}'))
                if not isinstance(args, dict):
                    raise ValueError('Invalid tool arguments')
                if event.get('name') == 'end_call':
                    self.ending = True
                    result = {'ok': True, 'ending': True}
                else:
                    result = await self.on_tool(event.get('name', ''), args)
                self.pending.append((ident, result))
            elif kind == 'response.done':
                self.speaking = False
                self.response_id = None
                if self.reply_pending:
                    # The response finished without saying anything the caller
                    # could hear; start the nudge clock now.
                    self.reply_since = asyncio.get_running_loop().time()
                pending, self.pending = self.pending, []
                for ident, result in pending:
                    await self.ws.send(json.dumps({'type': 'conversation.item.create', 'item': {
                        'type': 'function_call_output', 'call_id': ident,
                        'output': json.dumps(result, default=str)}}))
                if pending and not self.ending:
                    await self.ws.send(json.dumps({'type': 'response.create'}))

    async def watchdog(self):
        """Give a caller whose turn went unanswered one nudge, not dead air.

        The cancel-versus-completion race, a lost response or a silently dropped
        turn all leave the caller in silence. Re-asking the model once per turn
        turns that into an answer; repeated nudges could talk over the caller, so
        the debt is cleared when the nudge is sent.
        """
        while True:
            await asyncio.sleep(.25)
            if not self.reply_pending or self.speaking or self.caller_speaking or self.ending:
                continue
            if asyncio.get_running_loop().time() - self.reply_since < self.reply_nudge:
                continue
            self.reply_pending = False
            log.warning('Caller turn went unanswered for %.0fs; prompting the model',
                        self.reply_nudge)
            try:
                await self.ws.send(json.dumps({'type': 'response.create'}))
            except Exception:
                log.exception('Reply nudge could not be sent')
                return

    async def run(self):
        tasks = [asyncio.create_task(f()) for f in (self.input, self.output, self.grok, self.watchdog)]
        try:
            async with asyncio.timeout(MAX_SECONDS):
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def register(route, call_id):
    cfg = get_settings()
    if not cfg.phone_receptionist_enabled or cfg.phone_voice_provider != 'grok' or not cfg.xai_api_key:
        raise ValueError('Phone receptionist is disabled')
    tenant = await tenants.get_by_slug(route.tenant)
    if not tenant or not tenant['phone_enabled']:
        raise ValueError('Business receptionist is disabled')
    if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
        raise ValueError('Business has not enabled telephone answering')
    async with db.pool().acquire() as c:
        async with c.transaction():
            await c.execute('SELECT id FROM tenants WHERE id=$1 FOR UPDATE', tenant['id'])
            if not await c.fetchval('SELECT 1 FROM phone_numbers WHERE tenant_id=$1 AND e164=$2 AND enabled', tenant['id'], route.number):
                raise ValueError('Business route is not activated')
            used = await c.fetchval("SELECT count(*) FROM phone_calls WHERE tenant_id=$1 AND started_at>now()-interval '1 day'", tenant['id'])
            if used >= tenant['phone_daily_limit']:
                raise ValueError('Business call limit reached')
            # UNIQUE call_sid rejects replay, including cross-business reuse.
            await c.execute('INSERT INTO phone_calls(tenant_id,call_sid,from_number,to_number,status) VALUES($1,$2,$3,$4,$5)',
                            tenant['id'], call_id, '', route.number, 'in_progress')
    return tenant



async def prepare(route, call_id):
    """Create the call records and the Grok session for one route. Shared by the
    Python bridge and the internal voice shell."""
    tenant = await register(route, call_id)
    conversation = await convo.get_or_create(tenant, call_id, 'phone', None, None)
    await enquiries.capture(tenant, 'phone', call_id, 'Inbound telephone enquiry', conversation_id=conversation)
    capability = await voice_records.start(tenant, call_id, channel='phone')
    record_session = await voice_records.authenticate(capability['id'], capability['token'])
    session = voice.build_session(tenant, website=True)
    for direction in ('input', 'output'):
        session['audio'][direction]['format'] = {'type': 'audio/pcm', 'rate': 8000}
    # Telephone pacing needs a longer end-of-turn silence than the browser: a
    # caller dictating a number or an email address pauses mid-sentence. xAI
    # echoes these values back in session.updated.
    session['turn_detection'] = {'type': 'server_vad', 'silence_duration_ms': SILENCE_DURATION_MS,
                                 'prefix_padding_ms': 300}
    sms_ok = await sms_copy_available(tenant['id'])
    recording_ok = bool(get_settings().voice_recording_enabled
                        and await channel_authorization.is_authorized(tenant['id'], 'call_recording'))
    session['instructions'] = build_system_prompt(tenant, None, channel='phone') + phone_instructions(
        tenant['name'], recording_ok=recording_ok, listen_in=call_control.enabled(), sms_ok=sms_ok)
    session['tools'].append({'type':'function','name':'end_call','description':'End after saying goodbye.',
                             'parameters':{'type':'object','properties':{},'additionalProperties':False}})
    session['tools'].append({'type':'function','name':'set_call_recording',
        'description':'Start recording once the caller has been told calls are recorded (the greeting does this). Disable to discard audio if they object.',
        'parameters':{'type':'object','properties':{'enabled':{'type':'boolean'},'confirmed':{'type':'boolean'}},
                      'required':['enabled','confirmed'],'additionalProperties':False}})
    return {'tenant': tenant, 'conversation': conversation,
            'record_session': record_session, 'session': session}


async def run_phone_tool(tenant, record_session, conversation, call_id, name, args, recording=None):
    """Authorise and run one telephone tool. The Rust shell passes recording=None:
    it owns the audio buffer and applies the consent result itself."""
    if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
        raise ValueError('Business telephone authorization revoked')
    if name == 'set_call_recording':
        if args.get('enabled') is False:
            if recording is not None:
                recording.discard()
            record_session['recording_consent'] = False
        elif args.get('enabled') is True and args.get('confirmed') is True:
            if not (get_settings().voice_recording_enabled and await channel_authorization.is_authorized(tenant['id'], 'call_recording')):
                return {'ok':False, 'error':'Recording is unavailable; take a text message.'}
            if recording is not None:
                recording.start()
            record_session['recording_consent'] = True
        else:
            return {'ok':False, 'error':'Ask for explicit recording permission first.'}
        await db.pool().execute('UPDATE voice_sessions SET recording_consent=$2 WHERE id=$1', record_session['id'], record_session['recording_consent'])
        return {'ok':True, 'recording':record_session['recording_consent']}
    return await run_tool(tenant, name, args, {'voice_session':record_session, 'conversation_id':conversation, 'session_id':call_id,
                                              'channel':'phone', 'sender_phone':None})


async def finish(tenant, call_id, conversation, status, record_session=None, reason=''):
    async with db.pool().acquire() as c:
        async with c.transaction():
            row = await c.fetchrow('SELECT ended_at FROM phone_calls WHERE tenant_id=$1 AND call_sid=$2 FOR UPDATE', tenant['id'], call_id)
            if not row or row['ended_at']:
                return
            turns = await c.fetch("SELECT role,content FROM messages WHERE conversation_id=$1 AND role='user' ORDER BY id", conversation)
            text = '\n'.join(c for c in (clean_speech(r['content']) for r in turns) if c)
            if text:
                lead = await c.fetchrow('UPDATE leads SET message=$3,updated_at=now() WHERE tenant_id=$1 AND conversation_id=$2 RETURNING *', tenant['id'], conversation, text[-1000:])
                # Forward the voicemail as a private recording link when consent and
                # a recording exist, then close with the CRM note -- the same shape
                # the website-voice path uses, so the owner receives the audio, not
                # only the transcript.
                tail = ''
                if record_session and record_session.get('recording_consent'):
                    has_recording = await c.fetchval(
                        'SELECT 1 FROM voice_recordings WHERE tenant_id=$1 AND session_id=$2 AND conversation_id=$3',
                        tenant['id'], record_session['id'], conversation)
                    if has_recording:
                        token = secrets.token_urlsafe(32)
                        await c.execute(
                            'INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id) VALUES($1,$2,$3)',
                            voice_records.digest(token), record_session['id'], tenant['id'])
                        tail += '\n\nRecording (private link expires in 24 hours): ' + \
                            get_settings().public_base_url.rstrip('/') + '/api/v1/voice/recordings/shared/' + token
                tail += '\n\nThe complete enquiry is saved in your Concierge CRM.'
                owner = await c.fetchval('SELECT owner_number FROM managed_phone_setups WHERE tenant_id=$1', tenant['id'])
                # The managed-setup row is optional; without this fallback a real
                # call would notify only by email and silently skip the owner SMS.
                owner = owner or tenant.get('notify_phone')
                if owner:
                    await c.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,dedupe_key) VALUES($1,'owner_alert','sms',$2,$3,$4) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
                                    tenant['id'], owner, f"{tenant['name']} — new phone message:\n{text[:1100]}{tail}", call_id+':owner')
                if tenant.get('notify_email'):
                    await c.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,dedupe_key) VALUES($1,'owner_alert','email',$2,$3,$4,$5) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",
                                    tenant['id'], tenant['notify_email'], 'Phone message for '+tenant['name'], text[:24000] + tail, call_id+':owner-email')
                if lead:
                    await events.queue_twenty(tenant, 'voice.completed', call_id, {'lead': dict(lead)}, connection=c)
            await c.execute('UPDATE phone_calls SET status=$3,ended_at=now(),failure_reason=$4 WHERE tenant_id=$1 AND call_sid=$2', tenant['id'], call_id, status, reason[:500])


async def handle(reader, writer, route, networks):
    tenant = conversation = call_id = record_session = None
    recording = TelephoneRecording()
    status = 'failed'
    reason = ''
    try:
        peer = ipaddress.ip_address(writer.get_extra_info('peername')[0])
        if not any(peer in net for net in networks):
            raise ValueError('Untrusted AudioSocket peer')
        kind, body = await asyncio.wait_for(packet(reader), 5)
        if kind != 1 or len(body) != 16:
            raise ValueError('Expected AudioSocket call UUID')
        call_id = 'ast:'+str(uuid.UUID(bytes=body))
        prepared = await prepare(route, call_id)
        tenant = prepared['tenant']
        conversation = prepared['conversation']
        record_session = prepared['record_session']
        session = prepared['session']
        message_ids = {}
        async def transcript(role, text, item_id):
            key = (role, item_id)
            if item_id and key in message_ids:
                await db.pool().execute('UPDATE messages SET content=$3 WHERE conversation_id=$1 AND id=$2',
                                        conversation, message_ids[key], text)
            else:
                ident = await db.pool().fetchval('INSERT INTO messages(conversation_id,role,content) VALUES($1,$2,$3) RETURNING id',
                                                 conversation, role, text)
                if item_id:
                    message_ids[key] = ident
        async def tool(name, args):
            return await run_phone_tool(tenant, record_session, conversation, call_id, name, args, recording)
        async def monitor():
            while True:
                await asyncio.sleep(5)
                if recording.started is not None and not await channel_authorization.is_authorized(tenant['id'], 'call_recording'):
                    recording.discard()
                    record_session['recording_consent'] = False
                if not await channel_authorization.is_authorized(tenant['id'], 'telephone'):
                    raise ValueError('Business telephone authorization revoked')
        async with websockets.connect(get_settings().xai_realtime_url,
                additional_headers={'Authorization':'Bearer '+get_settings().xai_api_key}, open_timeout=15,
                max_size=2**20) as ws:
            media = asyncio.create_task(MediaBridge(reader, writer, ws, session, transcript, tool, recording).run())
            guard = asyncio.create_task(monitor())
            try:
                done, _ = await asyncio.wait((media, guard), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                media.cancel(); guard.cancel()
                await asyncio.gather(media, guard, return_exceptions=True)
        status = 'completed'
    except asyncio.IncompleteReadError:
        status = 'disconnected'
        reason = 'The audio stream closed before the call ended'
    except Exception as error:
        # Keep the message: "RuntimeError" alone cost a whole debugging session
        # after a real call went silent.
        log.warning('Asterisk call ended (%s): %s', type(error).__name__, str(error)[:500])
        reason = f'{type(error).__name__}: {str(error)[:300]}'
    finally:
        if tenant and conversation:
            try:
                body = recording.wav()
                if body and record_session:
                    try:
                        await voice_records.store_audio(record_session, body, 'audio/wav')
                    except Exception:
                        log.exception('Telephone recording could not be saved')
                await finish(tenant, call_id, conversation, status, record_session, reason=reason)
                if record_session:
                    request = await db.pool().fetchval('UPDATE voice_sessions SET finalized_at=now() WHERE id=$1 RETURNING delivery_request', record_session['id'])
                    await voice_records.complete_delivery(record_session, tenant, request, {'ok':True})
            except Exception:
                log.exception('Asterisk call finalization requires reconciliation')
        writer.close()
        await writer.wait_closed()


async def main():
    routes = routes_from_json(os.environ['ASTERISK_ROUTES'])
    host = os.environ.get('ASTERISK_BIND', '127.0.0.1')
    networks = [ipaddress.ip_network(s.strip()) for s in os.environ.get('ASTERISK_PEERS', '127.0.0.1/32,::1/128').split(',')]
    if any(n.prefixlen == 0 for n in networks):
        raise ValueError('An unrestricted AudioSocket peer network is forbidden')
    await db.init()
    servers = []
    try:
        for route in routes:
            server = await asyncio.start_server(lambda r,w,route=route:handle(r,w,route,networks), host, route.port)
            servers.append(server)
            log.info('Business %s private phone listener ready on %s:%s', route.tenant, host, route.port)
        await asyncio.gather(*(s.serve_forever() for s in servers))
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()
        await db.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
