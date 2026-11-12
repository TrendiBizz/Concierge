import asyncio
import base64
import json
import struct
import uuid

import pytest
from app.asterisk_bridge import MAX_ERRORS, MediaBridge, routes_from_json, packet


def test_routes_cannot_share_destination_or_port():
    a = {'tenant':'alpha','number':'+6495550100','port':9101}
    b = {'tenant':'beta','number':'+6495550101','port':9102}
    assert len(routes_from_json(json.dumps([a,b]))) == 2
    for bad in ({**b,'port':9101},{**b,'number':a['number']}):
        with pytest.raises(ValueError):
            routes_from_json(json.dumps([a,bad]))


class Socket:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.sent = []
    async def send(self, value):
        self.sent.append(json.loads(value))
    def __aiter__(self):
        return self
    async def __anext__(self):
        return json.dumps(await self.inbox.get())


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.005)


@pytest.mark.hangs_on_py312
def test_two_concurrent_businesses_audio_transcript_tools_and_barge_in_are_isolated():
    async def scenario():
        results = {}
        tasks = []
        servers = []
        clients = []
        try:
            for index, business in enumerate(('alpha','beta')):
                ws = Socket()
                turns, tools = [], []
                async def transcript(role, text, item_id, turns=turns):
                    turns.append((role,text,item_id))
                async def tool(name, args, tools=tools, business=business):
                    tools.append((business,name,args))
                    return {'business':business}
                async def connected(reader, writer, ws=ws, business=business, transcript=transcript, tool=tool):
                    task=asyncio.create_task(MediaBridge(reader,writer,ws,{'instructions':business},transcript,tool).run())
                    tasks.append(task)
                server=await asyncio.start_server(connected,'127.0.0.1',0)
                servers.append(server)
                reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
                clients.append(writer)
                results[business]=(ws,turns,tools,reader,writer,bytes([index+1,0])*160)
            for business,(ws,turns,tools,reader,writer,audio) in results.items():
                await until(lambda:ws.sent)
                assert ws.sent[0]['session']['instructions']==business
                await ws.inbox.put({'type':'session.updated'})
                await until(lambda:len(ws.sent)>=2)
                writer.write(struct.pack('!BH',0x10,len(audio))+audio)
                await writer.drain()
                await ws.inbox.put({'type':'response.created'})
                await ws.inbox.put({'type':'response.output_audio.delta','delta':base64.b64encode(audio).decode()})
                await ws.inbox.put({'type':'conversation.item.input_audio_transcription.completed','item_id':'same-id','transcript':business+' enquiry'})
                await ws.inbox.put({'type':'conversation.item.input_audio_transcription.completed','item_id':'same-id','transcript':business+' enquiry'})
                await ws.inbox.put({'type':'conversation.item.input_audio_transcription.completed','item_id':'same-id','transcript':business+' enquiry complete'})
                await ws.inbox.put({'type':'response.function_call_arguments.done','name':'search_knowledge','call_id':'same-tool-id','arguments':'{}'})
                await ws.inbox.put({'type':'response.done'})
            for business,(ws,turns,tools,reader,writer,audio) in results.items():
                kind,body=await asyncio.wait_for(packet(reader),2)
                assert kind==0x10 and body==audio
                await until(lambda:turns and tools and any(e['type']=='input_audio_buffer.append' for e in ws.sent))
                assert turns==[('user',business+' enquiry','same-id'),('user',business+' enquiry complete','same-id')]
                assert tools==[(business,'search_knowledge',{})]
                assert base64.b64decode(next(e['audio'] for e in ws.sent if e['type']=='input_audio_buffer.append'))==audio
                outputs=[json.loads(e['item']['output']) for e in ws.sent if e['type']=='conversation.item.create']
                assert outputs==[{'business':business}]
                await ws.inbox.put({'type':'response.created'})
                await ws.inbox.put({'type':'input_audio_buffer.speech_started'})
                await until(lambda:any(e['type']=='response.cancel' for e in ws.sent))
                writer.write(b'\x00\x00\x00')
                await writer.drain()
            await asyncio.wait_for(asyncio.gather(*tasks),2)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            for writer in clients:
                writer.close()
                await writer.wait_closed()
            for server in servers:
                server.close()
                await server.wait_closed()
    asyncio.run(scenario())


def test_shared_sip_provider_has_exact_destination_mapping_and_unknown_rejection():
    import runpy
    from pathlib import Path
    renderer=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/asterisk/render_routes.py'))['render']
    rows=[{'tenant':'alpha','number':'+6495550100','port':9101,'source_cidr':'192.0.2.10/32'},
          {'tenant':'beta','number':'+6495550101','port':9102,'source_cidr':'192.0.2.10/32'}]
    extensions,pjsip=renderer(rows,'bridge')
    assert 'exten => +6495550100,1,Goto(business-alpha,s,1)' in extensions
    assert 'exten => +6495550101,1,Goto(business-beta,s,1)' in extensions
    assert 'exten => _.,1,Hangup(21)' in extensions
    assert 'bridge:9101' in extensions and 'bridge:9102' in extensions
    assert pjsip.count('type=endpoint')==1
    with pytest.raises(ValueError):renderer([rows[0],{**rows[1],'number':rows[0]['number']}],'bridge')
    with pytest.raises(ValueError):renderer([{**rows[0],'source_cidr':'0.0.0.0/0'}],'bridge')


def test_oversized_or_truncated_audio_socket_packets_are_rejected():
    async def scenario():
        reader=asyncio.StreamReader()
        reader.feed_data(struct.pack('!BH',0x10,9000))
        with pytest.raises(ValueError):await packet(reader)
        reader=asyncio.StreamReader()
        reader.feed_data(struct.pack('!BH',0x10,320)+b'\0'*10)
        reader.feed_eof()
        with pytest.raises(asyncio.IncompleteReadError):await packet(reader)
    asyncio.run(scenario())


def test_silent_asterisk_endpoint_supplies_vad_silence_without_cancelling_partial_packet():
    async def scenario():
        reader=asyncio.StreamReader()
        ws=Socket()
        bridge=MediaBridge(reader,None,ws,{},None,None)
        bridge.ready.set()
        task=asyncio.create_task(bridge.input())
        try:
            audio=b'\x01\x00'*160
            frame=struct.pack('!BH',0x10,len(audio))+audio
            reader.feed_data(frame[:4])
            await asyncio.sleep(.06)
            assert ws.sent and all(base64.b64decode(e['audio'])==b'\0'*320 for e in ws.sent)
            reader.feed_data(frame[4:])
            await until(lambda:any(base64.b64decode(e['audio'])==audio for e in ws.sent))
            reader.feed_data(b'\0\0\0')
            await asyncio.wait_for(task,1)
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
    asyncio.run(scenario())


def test_a_cancel_that_races_response_completion_does_not_end_the_call():
    # A real call died in dead air: VAD re-fired speech_started right after a
    # reply started, the bridge sent response.cancel, xAI answered
    # "Cancellation failed: no active response found", and the old code treated
    # any error event as fatal -- killing the whole call.
    async def scenario():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None)
        task = asyncio.create_task(bridge.grok())
        try:
            await ws.inbox.put({'type':'session.updated'})
            await until(lambda: any(e['type']=='response.create' for e in ws.sent))
            await ws.inbox.put({'type':'response.created','response_id':'r1'})
            await ws.inbox.put({'type':'input_audio_buffer.speech_started','item_id':'u1'})
            await until(lambda: any(e['type']=='response.cancel' for e in ws.sent))
            await ws.inbox.put({'type':'response.done','response_id':'r1'})
            benign = {'type':'error','error':{'type':'invalid_request_error',
                                              'code':'invalid_request_error',
                                              'message':'Cancellation failed: no active response found'}}
            for _ in range(MAX_ERRORS-1):
                await ws.inbox.put(benign)
                await asyncio.sleep(.02)
            assert not task.done(), 'one benign race must not end the call'
            await ws.inbox.put(benign)
            with pytest.raises(RuntimeError):
                await asyncio.wait_for(task, 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_duplicate_speech_started_for_a_finished_turn_never_cancels_the_reply():
    async def scenario():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None)
        task = asyncio.create_task(bridge.grok())
        try:
            await ws.inbox.put({'type':'session.updated'})
            await until(lambda: any(e['type']=='response.create' for e in ws.sent))
            await ws.inbox.put({'type':'input_audio_buffer.speech_started','item_id':'u1'})
            await ws.inbox.put({'type':'input_audio_buffer.speech_stopped','item_id':'u1'})
            await ws.inbox.put({'type':'response.created','response_id':'r2'})
            await ws.inbox.put({'type':'input_audio_buffer.speech_started','item_id':'u1'})
            await asyncio.sleep(.05)
            assert not any(e['type']=='response.cancel' for e in ws.sent)
            await ws.inbox.put({'type':'input_audio_buffer.speech_started','item_id':'u2'})
            await until(lambda: any(e['type']=='response.cancel' for e in ws.sent))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_an_unanswered_caller_turn_is_prompted_once_instead_of_going_silent():
    async def scenario():
        ws = Socket()
        bridge = MediaBridge(None, None, ws, {}, None, None, reply_nudge=.2)
        bridge.reply_pending = True
        bridge.reply_since = asyncio.get_running_loop().time()
        task = asyncio.create_task(bridge.watchdog())
        try:
            await until(lambda: any(e['type']=='response.create' for e in ws.sent))
            assert sum(e['type']=='response.create' for e in ws.sent) == 1
            await asyncio.sleep(.4)
            assert sum(e['type']=='response.create' for e in ws.sent) == 1, 'one nudge per turn'
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
