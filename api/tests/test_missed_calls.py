"""Missed-call text-back: the rules, the message, the queue and the sweep.

The decision rules are pure, so most of this runs without a database. The two integration-shaped
tests use a fake pool the same way test_outbox_reconcile.py does.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app import missed_calls

NOW = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)


def tenant(**over):
    base = {"id": "t1", "name": "Pukeko Construction", "missed_call_textback": True,
            "sms_enabled": True, "sms_from": "+6421000000", "booking_url": "",
            "missed_call_template": "", "default_country_code": "64", "timezone": "Pacific/Auckland"}
    base.update(over)
    return base


def call(**over):
    base = {"call_sid": "sip:abc", "tenant_id": "t1", "from_number": "+64211234567",
            "to_number": "+6490000000", "status": "completed",
            "started_at": NOW - timedelta(seconds=8), "ended_at": NOW, "session_id": "sip:abc"}
    base.update(over)
    return base


def decide(**over):
    args = dict(tenant=tenant(), call=call(), caller_turns=0, has_appointment=False,
                recovered_recently=False, sms_authorized=True, now=NOW)
    args.update(over)
    return missed_calls.decide(**args)


def test_a_silent_hangup_is_texted_back():
    assert decide() == ("text", "hung_up_before_answering")


def test_a_silent_call_that_ran_long_is_still_recovered():
    # The caller listened to the greeting and hung up. Duration alone must not disqualify them:
    # the signal that matters is that they never had a turn.
    assert decide(call=call(started_at=NOW - timedelta(seconds=45)))[0] == "text"


def test_a_short_call_where_the_caller_spoke_is_still_recovered():
    assert decide(caller_turns=1, call=call(started_at=NOW - timedelta(seconds=5)))[0] == "text"


def test_a_real_conversation_is_not_recovered():
    action, reason = decide(caller_turns=3, call=call(started_at=NOW - timedelta(minutes=3)))
    assert (action, reason) == ("skip", "call_was_answered")


def test_switched_off_means_no_text():
    assert decide(tenant=tenant(missed_call_textback=False)) == ("skip", "textback_disabled")


def test_sms_must_be_enabled_and_authorised():
    assert decide(tenant=tenant(sms_enabled=False)) == ("skip", "sms_disabled")
    assert decide(sms_authorized=False) == ("skip", "sms_not_authorized")


def test_no_caller_number_means_nothing_to_text():
    assert decide(call=call(from_number="")) == ("skip", "no_caller_number")


def test_a_business_failing_back_to_its_own_number_is_skipped():
    assert decide(call=call(from_number="+6490000000")) == ("skip", "self_call")


def test_a_booking_beats_a_text_back():
    assert decide(has_appointment=True) == ("skip", "already_booked")


def test_one_reply_per_number_per_day():
    assert decide(recovered_recently=True) == ("skip", "recovered_recently")


def test_a_live_call_is_left_alone_until_it_is_stale():
    live = call(status="in_progress", ended_at=None, started_at=NOW - timedelta(seconds=10))
    assert decide(call=live) == ("skip", "call_in_progress")
    stale = call(status="ringing", ended_at=None, started_at=NOW - timedelta(minutes=5))
    assert decide(call=stale)[0] == "text"


def test_provider_no_answer_statuses_are_recovered_even_without_an_end_time():
    for status in ("missed", "no-answer", "busy", "failed", "canceled"):
        assert decide(call=call(status=status, ended_at=None))[0] == "text", status


def test_message_defaults_to_a_reply_invitation():
    assert "Reply to this message" in missed_calls.compose_message(tenant(), "")


def test_message_appends_the_booking_link_when_one_exists():
    body = missed_calls.compose_message(tenant(), "https://example.test/book")
    assert "https://example.test/book" in body


def test_a_template_with_a_placeholder_gets_the_link_substituted():
    body = missed_calls.compose_message(
        tenant(missed_call_template="Sorry! Pick a time: {link}"), "https://example.test/book")
    assert body == "Sorry! Pick a time: https://example.test/book"
    empty = missed_calls.compose_message(
        tenant(missed_call_template="Sorry! Pick a time:{link}"), "")
    assert "{" not in empty and "}" not in empty


def test_a_tenant_template_without_a_placeholder_still_carries_the_link():
    body = missed_calls.compose_message(
        tenant(missed_call_template="Sorry we missed you."), "https://example.test/book")
    assert body.startswith("Sorry we missed you.")
    assert "https://example.test/book" in body


class FakePool:
    """Records every statement; answers the handful of reads evaluate_call needs."""

    def __init__(self, *, turns=0, appointment=False, recent=False, outbox_id=77):
        self.turns, self.appointment, self.recent, self.outbox_id = turns, appointment, recent, outbox_id
        self.executed = []
        self.fetched = []

    async def fetchval(self, sql, *args):
        text = " ".join(sql.split())
        if "count(*) FROM messages" in text:
            return self.turns
        if "FROM appointments" in text:
            return 1 if self.appointment else None
        if "FROM missed_call_recoveries" in text:
            return 1 if self.recent else None
        if "SELECT id FROM outbox" in text:
            return self.outbox_id
        return None

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "INSERT 0 1"

    async def fetch(self, sql, *args):
        self.fetched.append((" ".join(sql.split()), args))
        return []

    async def fetchrow(self, sql, *args):
        return None


def test_recovery_queues_one_sms_and_records_the_decision(monkeypatch):
    pool = FakePool(turns=0)
    queued = {}

    async def fake_enqueue(tenant_id, kind, channel, to_addr, body, **kw):
        queued.update(tenant_id=tenant_id, kind=kind, channel=channel, to=to_addr,
                      body=body, dedupe=kw.get("dedupe_key"))
        return True

    captured = {}

    async def fake_capture(tenant, channel, source, message, **kw):
        captured.update(channel=channel, source=source, phone=kw.get("phone"), message=message)
        return {"id": "lead-1"}

    async def authorized(*_a, **_k):
        return True

    monkeypatch.setattr(missed_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(missed_calls.outbox, "enqueue", fake_enqueue)
    monkeypatch.setattr(missed_calls.enquiries, "capture", fake_capture)
    monkeypatch.setattr(missed_calls.channel_authorization, "is_authorized", authorized)

    result = asyncio.run(missed_calls.evaluate_call(tenant(), call()))

    assert result["action"] == "text"
    assert queued["channel"] == "sms" and queued["kind"] == "missed_call"
    assert queued["to"] == "+64211234567"
    assert queued["dedupe"] == f"missed:t1:+64211234567:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    assert captured["channel"] == "phone" and captured["phone"] == "+64211234567"
    assert captured["source"] == "missed:sip:abc"
    # The decision row is written with the outbox link so the owner sees what was sent.
    inserts = [row for row in pool.executed if "INSERT INTO missed_call_recoveries" in row[0]]
    assert inserts and inserts[-1][1][3] == "queued"
    assert inserts[-1][1][5] == 77


def test_a_skipped_call_records_why_and_sends_nothing(monkeypatch):
    pool = FakePool(appointment=True)
    sent = []

    async def fake_enqueue(*a, **k):
        sent.append((a, k))
        return True

    async def authorized(*_a, **_k):
        return True

    monkeypatch.setattr(missed_calls.db, "pool", lambda: pool)
    monkeypatch.setattr(missed_calls.outbox, "enqueue", fake_enqueue)
    monkeypatch.setattr(missed_calls.channel_authorization, "is_authorized", authorized)

    result = asyncio.run(missed_calls.evaluate_call(tenant(), call()))

    assert result == {"action": "skip", "reason": "already_booked"}
    assert sent == []
    inserts = [row for row in pool.executed if "INSERT INTO missed_call_recoveries" in row[0]]
    assert inserts[-1][1][3] == "skipped"
    assert inserts[-1][1][4] == "already_booked"


def test_sweep_only_looks_at_ended_untouched_calls(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(missed_calls.db, "pool", lambda: pool)

    assert asyncio.run(missed_calls.sweep()) == 0
    sql, args = pool.fetched[0]
    assert "ended_at IS NOT NULL" in sql
    assert "missed_call_recoveries" in sql
    assert args[0] == 100


def test_evaluate_call_sid_separates_the_tenant_from_the_call(monkeypatch):
    pool = FakePool()
    seen = {}

    async def fake_evaluate(tenant, call):
        seen["tenant"], seen["call"] = tenant, call
        return {"action": "skip", "reason": "stub"}

    class RowPool(FakePool):
        async def fetchrow(self, sql, *args):
            return {"call_sid": "sip:abc", "tenant_id": "t1", "session_id": "sip:abc",
                    "from_number": "+64211234567", "to_number": "+6490000000",
                    "status": "completed", "started_at": NOW, "ended_at": NOW,
                    "id": "t1", "name": "Pukeko", "missed_call_textback": True,
                    "sms_enabled": True, "timezone": "Pacific/Auckland", "booking_url": ""}

    monkeypatch.setattr(missed_calls.db, "pool", lambda: RowPool())
    monkeypatch.setattr(missed_calls, "evaluate_call", fake_evaluate)

    assert asyncio.run(missed_calls.evaluate_call_sid("sip:abc"))["reason"] == "stub"
    assert seen["tenant"]["id"] == "t1" and seen["tenant"]["name"] == "Pukeko"
    assert seen["call"]["call_sid"] == "sip:abc"
    assert "name" not in seen["call"]
