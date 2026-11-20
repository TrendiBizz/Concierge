"""The owner's end-of-call alert: summary, full two-sided transcript, no blank call-start alert."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import asterisk_bridge, call_alert, call_insights, enquiries, voice_internal
from app.speech_text import strip_control_tags

TENANT = {'id': 't1', 'name': 'Test Joinery', 'notify_email': 'owner@example.test',
          'notify_phone': '+15550100', 'timezone': 'Pacific/Auckland'}
TAG = '<response_segment_0_already_spoken>'
ROWS = [{'role': 'assistant', 'content': TAG + 'Hello, how can I help?'},
        {'role': 'user', 'content': 'Um, I need a deck quoted, 4 by 6 metres.'},
        {'role': 'assistant', 'content': 'Can I take your name and number?'},
        {'role': 'user', 'content': 'Yes. Sam Example, 021 555 0100.'}]
INSIGHT = {'summary': 'Sam Example wants a 4x6m deck quoted; call 021 555 0100.', 'outcome': 'quote_requested',
           'next_step': 'Ring Sam with a quote.'}


class Conn:
    def __init__(self, ended=None):
        self.executed, self.ended = [], ended

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetchrow(self, sql, *a):
        return {'ended_at': self.ended}

    async def fetchval(self, sql, *a):
        return None  # no managed owner number, no recording

    async def execute(self, sql, *a):
        self.executed.append((sql, a))


def run_finish(monkeypatch, rows, *, analysis=INSIGHT, number='+15550123', lead=None, analyse=None):
    conn = Conn()
    call = {'call_sid': 'ast:1', 'session_id': None, 'from_number': number, 'ended_at': None,
            'started_at': datetime(2026, 11, 20, 4, 12, tzinfo=timezone.utc)}
    pool = SimpleNamespace(
        fetchrow=AsyncMock(side_effect=lambda sql, *a: dict(call) if 'phone_calls' in sql else lead),
        fetch=AsyncMock(return_value=rows), acquire=lambda: conn)
    monkeypatch.setattr(asterisk_bridge.db, 'pool', lambda: pool)
    capture = AsyncMock(return_value={'name': 'Sam Example', 'phone': '+15550123', 'email': ''})
    monkeypatch.setattr(enquiries, 'capture', capture)
    monkeypatch.setattr(call_insights, 'analyse_call', analyse or AsyncMock())
    monkeypatch.setattr(call_insights, 'stored', AsyncMock(return_value=analysis))
    asyncio.run(asterisk_bridge.finish(TENANT, 'ast:1', 'conv', 'completed'))
    sms = [a for sql, a in conn.executed if 'INTO outbox' in sql and "'sms'" in sql]
    emails = [a for sql, a in conn.executed if 'INTO outbox' in sql and "'email'" in sql]
    conn.sms, conn.emails = sms, emails
    return emails, capture, conn


def test_alert_has_summary_then_full_two_sided_transcript_without_markup(monkeypatch):
    emails, capture, conn = run_finish(monkeypatch, ROWS)
    assert len(emails) == 1 and emails[0][-1] == 'ast:1:owner-email'
    body = emails[0][3]
    assert body.startswith('Summary: Sam Example wants a 4x6m deck')
    assert body.index('Summary:') < body.index('Caller: Um, I need a deck') < body.index('Receptionist: Can I take')
    assert 'Receptionist: Hello, how can I help?' in body and 'Caller: Yes. Sam Example' in body
    assert 'already_spoken' not in body
    assert body.endswith('The complete enquiry is saved in your Concierge CRM.')
    assert emails[0][2] == 'Phone message for Test Joinery'
    # the lead is made here, with no second "Phone enquiry" alert
    assert capture.await_args.kwargs['notify_owner'] is False
    assert any('UPDATE phone_calls SET status' in sql for sql, _ in conn.executed)


def test_sms_carries_the_same_content_summary_first(monkeypatch):
    _, _, conn = run_finish(monkeypatch, ROWS)
    assert len(conn.sms) == 1 and conn.sms[0][3] == 'ast:1:owner'
    text = conn.sms[0][2]
    assert text.index('Summary:') < text.index('Receptionist: Hello') < text.index('Caller: Yes.')


def test_long_transcript_is_sent_as_ordered_sms_parts_not_truncated():
    body = 'Summary: wants a deck\n\nFull transcript:\n' + '\n'.join(f'Caller: line {i} ' + 'x' * 100 for i in range(60))
    parts = call_alert.sms_parts('Test Joinery', body)
    assert 1 < len(parts) <= call_alert.SMS_MAX_PARTS
    assert all(len(p) <= call_alert.SMS_PART + 20 for p in parts)
    assert 'Summary: wants a deck' in parts[0] and parts[0].startswith('(1/')
    assert 'line 0 ' in parts[0] or 'line 0 ' in parts[1]
    short = call_alert.sms_parts('T', 'Summary: s')
    assert len(short) == 1 and not short[0].startswith('(')


def test_model_failure_still_sends_a_deterministic_summary(monkeypatch):
    emails, *_ = run_finish(monkeypatch, ROWS, analysis=None, analyse=AsyncMock(side_effect=RuntimeError('model down')))
    body = emails[0][3]
    assert 'Summary: Sam Example called. They said:' in body and 'deck quoted' in body
    assert 'Caller: Yes. Sam Example' in body


def test_zero_turn_call_makes_no_lead_and_only_a_missed_call_alert(monkeypatch):
    email, capture, _ = run_finish(monkeypatch, [{'role': 'assistant', 'content': TAG + 'Hello?'}])
    capture.assert_not_awaited()
    assert len(email) == 1 and email[0][2] == 'Missed call for Test Joinery'
    assert email[0][3].startswith('Missed call from +15550123 at 20 Nov 17:12, no message left.')
    assert 'Channel:' not in email[0][3]


def test_zero_turn_call_with_unknown_number_alerts_nobody(monkeypatch):
    emails, capture, conn = run_finish(monkeypatch, [], number='')
    assert emails == [] and conn.sms == [] and capture.await_count == 0


def test_dedupe_keys_make_a_rerun_idempotent_and_ended_calls_are_skipped(monkeypatch):
    _, _, conn = run_finish(monkeypatch, ROWS)
    inserts = [sql for sql, _ in conn.executed if 'INTO outbox' in sql]
    assert inserts and all('ON CONFLICT(dedupe_key)' in sql for sql in inserts)
    assert [a[3] for a in conn.sms] == ['ast:1:owner']
    conn = Conn()
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={'ended_at': datetime.now(), 'from_number': ''}),
                           fetch=AsyncMock(), acquire=lambda: conn)
    monkeypatch.setattr(asterisk_bridge.db, 'pool', lambda: pool)
    asyncio.run(asterisk_bridge.finish(TENANT, 'ast:1', 'conv', 'completed'))
    assert conn.executed == []


def test_prepare_no_longer_creates_a_lead_or_alert_at_call_start():
    import inspect
    assert 'enquiries.capture' not in inspect.getsource(asterisk_bridge.prepare)


def test_leaked_tags_are_stripped_in_the_api_store_path(monkeypatch):
    assert strip_control_tags(TAG + 'Hello</response_segment_0_already_spoken>') == 'Hello'
    assert strip_control_tags('2 < 3 and 4 > 1') == '2 < 3 and 4 > 1'
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={'id': 1}))
    monkeypatch.setattr(voice_internal.db, 'pool', lambda: pool)
    monkeypatch.setattr(voice_internal, '_authorize', lambda t: None)
    body = voice_internal.Transcript(conversation_id='c', role='assistant', text=TAG + 'Hi there', item_id='i')
    asyncio.run(voice_internal.transcript(body))
    assert pool.fetchrow.await_args.args[3] == 'Hi there'
