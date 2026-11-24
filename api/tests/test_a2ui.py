"""Protocol and trust-boundary regression coverage, without model calls."""
import copy
import json
from pathlib import Path
import pytest
from app import a2ui


def test_all_cards_are_adjacency_lists_and_have_bound_actions():
    for kind, fields in a2ui.FIELDS.items():
        updates, model, begin = a2ui.card(kind)
        sid = begin['beginRendering']['surfaceId']
        assert updates['surfaceUpdate']['surfaceId'] == model['dataModelUpdate']['surfaceId'] == sid
        components = {c['id']: c['component'] for c in updates['surfaceUpdate']['components']}
        assert components['root']['Card']['child'] == 'column'
        action = components['submit']['Button']['action']
        assert action['name'] == 'submit_' + kind
        assert {e['key'] for e in action['context']} == set(fields)
        for entry in action['context']:
            assert entry['value'] == {'path': '/' + entry['key']}
        assert set(components['column']['Column']['children']['explicitList']) <= set(components)


def _action(kind='quote'):
    return {'name':'submit_'+kind, 'surfaceId':a2ui.card(kind)[-1]['beginRendering']['surfaceId'],
            'sourceComponentId':'submit', 'context':{'email':'request@example.test','details':'Example request'}}


def test_action_values_preserved():
    action = _action()
    assert a2ui.validate_action(action) == ('quote', action['context'])


@pytest.mark.parametrize('change',[
    {'name':'run_tool'}, {'sourceComponentId':'other'}, {'surfaceId':'other'},
    {'context':{'email':'bad','details':'Example'}},
    {'context':{'email':'request@example.test','details':'Example','price':'1'}},
    {'context':{'email':'request@example.test','details':''}},
])
def test_untrusted_actions_rejected(change):
    action = _action(); action.update(change)
    with pytest.raises(ValueError): a2ui.validate_action(action)


def test_booking_requires_future_time_and_real_timezone():
    action = _action('booking')
    action['context'] = {'email':'request@example.test','when':'2027-06-15T14:30','timezone':'Pacific/Auckland'}
    assert a2ui.validate_action(action)[0] == 'booking'
    for key,value in [('when','2020-01-01T12:00'),('timezone','not-a-zone')]:
        invalid=copy.deepcopy(action);invalid['context'][key]=value
        with pytest.raises(ValueError): a2ui.validate_action(invalid)


def test_trendi_price_never_offered_for_other_tenants():
    assert a2ui.choose('pricing', {'slug':'concierge'}) == 'pricing'
    assert a2ui.choose('pricing', {'slug':'trendi-oauth-staging'}) == 'pricing'
    assert a2ui.choose('pricing', {'slug':'example-business'}) is None
    assert 'USD $250/month' in a2ui.TEXT['pricing']
    assert '3-month minimum' in a2ui.TEXT['pricing']
    assert 'no slot is reserved' in a2ui.TEXT['booking']


def test_every_html_page_has_exactly_one_widget():
    root=Path(__file__).resolve().parents[2]
    inventory=json.loads((root/'tools/a2ui/pages.json').read_text())
    assert {x['file'] for x in inventory} == {str(p.relative_to(root/'website')) for p in (root/'website').rglob('*.html')}
    for entry in inventory:
        assert (root/'website'/entry['file']).read_text().count('https://chat.trendibizz.com/widget.js') == 1


def test_public_stream_negotiation_and_pause(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.routers import public
    async def tenant_for(*args): return {'id':'test', 'slug':'concierge'}
    monkeypatch.setattr(public, '_main', lambda: SimpleNamespace(_rate_limit=lambda *a:None, _tenant_for=tenant_for))
    async def scenario(capability, suppressed):
        async def stream(*args, **kwargs):
            yield {'type':'done','reply':'Text remains available','suppressed':suppressed}
        monkeypatch.setattr(public.chat_engine,'run_turn_stream',stream)
        request=public.ChatRequest(key='test',session_id='test-session',message='quote',a2ui_version=capability)
        response=await public.chat_stream(request,None)
        return ''.join([chunk async for chunk in response.body_iterator])
    assert 'surfaceUpdate' in asyncio.run(scenario('0.8',False))
    assert 'surfaceUpdate' not in asyncio.run(scenario(None,False))
    assert 'surfaceUpdate' not in asyncio.run(scenario('0.8',True))


def test_action_handler_routes_values_to_enquiry(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.routers import public
    from app import convo, enquiries
    calls=[]
    async def tenant_for(*args): return {'id':'test', 'slug':'concierge'}
    async def conversation(*args): return 'test-conversation'
    async def save(*args): calls.append(('message',args))
    async def capture(*args, **kwargs): calls.append(('capture',args,kwargs))
    monkeypatch.setattr(public,'_main',lambda: SimpleNamespace(_rate_limit=lambda *a:None,_tenant_for=tenant_for))
    monkeypatch.setattr(convo,'get_or_create',conversation)
    monkeypatch.setattr(convo,'save_message',save)
    monkeypatch.setattr(enquiries,'capture',capture)
    action=_action();action['timestamp']='2026-11-24T01:00:00Z'
    req=public.A2UIActionRequest(key='test',session_id='test-session',userAction=action)
    result=asyncio.run(public.a2ui_action(req,None))
    capture_call=next(c for c in calls if c[0]=='capture')
    assert json.loads(capture_call[1][3].split(': ',1)[1]) == action['context']
    assert capture_call[2]['conversation_id']=='test-conversation'
    assert result['a2ui'][-1]['beginRendering']['surfaceId'].startswith('cc-confirmation-')

    assert capture_call[2]['email']=='request@example.test'
    assert capture_call[1][2].endswith(':'+action['surfaceId'])
    count=len([c for c in calls if c[0]=='capture'])
    confirmation={'name':'submit_confirmation','surfaceId':result['a2ui'][-1]['beginRendering']['surfaceId'],
                  'sourceComponentId':'submit','timestamp':'2026-11-24T01:00:00Z','context':{}}
    asyncio.run(public.a2ui_action(public.A2UIActionRequest(key='test',session_id='test-session',userAction=confirmation),None))
    assert len([c for c in calls if c[0]=='capture'])==count
