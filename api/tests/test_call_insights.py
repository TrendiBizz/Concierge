"""Item D — after-call intelligence: parsing, deterministic shortcuts, persistence, follow-ups."""
import asyncio
import json

from app import call_insights


# ------------------------------------------------------------------ parsing

def test_a_clean_json_reply_is_parsed():
    raw = json.dumps({"summary": "Caller asked for a driveway quote.",
                      "outcome": "quote_requested", "sentiment": "positive",
                      "next_step": "Send the quote today."})
    assert call_insights.parse_analysis(raw) == {
        "summary": "Caller asked for a driveway quote.",
        "outcome": "quote_requested",
        "sentiment": "positive",
        "next_step": "Send the quote today.",
    }


def test_a_fenced_or_padded_reply_is_still_parsed():
    raw = 'Here you go:\n```json\n{"summary":"Booked for Tuesday","outcome":"booked","sentiment":"positive","next_step":"none"}\n```'
    result = call_insights.parse_analysis(raw)
    assert result["outcome"] == "booked" and result["next_step"] == ""


def test_an_unknown_outcome_becomes_unresolved_and_sentiment_becomes_neutral():
    raw = '{"summary":"Something happened","outcome":"teleported","sentiment":"ecstatic","next_step":"x"}'
    result = call_insights.parse_analysis(raw)
    assert result["outcome"] == "unresolved"
    assert result["sentiment"] == "neutral"


def test_unusable_replies_are_rejected_rather_than_half_trusted():
    for raw in ("", "   ", "no json here", "{broken", "[]", None, 42,
                '{"outcome":"booked"}', '{"summary":"   ","outcome":"booked"}'):
        assert call_insights.parse_analysis(raw) is None, raw


def test_whitespace_and_length_are_normalised():
    raw = '{"summary":"  lots\\n\\n of   spaces  ","outcome":"booked","sentiment":"neutral","next_step":"  -  "}'
    result = call_insights.parse_analysis(raw)
    assert result["summary"] == "lots of spaces"
    assert result["next_step"] == ""
    long = call_insights.parse_analysis(json.dumps(
        {"summary": "x" * 900, "outcome": "booked", "sentiment": "neutral", "next_step": ""}))
    assert len(long["summary"]) == 400


# ------------------------------------------------------------------ deterministic rules

def test_a_call_nobody_spoke_on_is_not_analysed():
    assert call_insights.deterministic_outcome(appointment_created=False, caller_turns=0) == "no_conversation"
    assert call_insights.deterministic_outcome(appointment_created=True, caller_turns=0) == "no_conversation"


def test_an_appointment_is_booked_without_asking_the_model():
    assert call_insights.deterministic_outcome(appointment_created=True, caller_turns=4) == "booked"
    assert call_insights.deterministic_outcome(appointment_created=False, caller_turns=4) is None


def test_only_callback_and_unresolved_need_a_task():
    assert call_insights.needs_follow_up("call_back") is True
    assert call_insights.needs_follow_up("unresolved") is True
    for outcome in ("booked", "quote_requested", "information_only", "not_interested", "wrong_number"):
        assert call_insights.needs_follow_up(outcome) is False


# ------------------------------------------------------------------ persistence

class FakePool:
    def __init__(self, turns=None, lead=None, appointment=False, done=False, cap=0,
                 existing_task=False):
        self.turns = turns if turns is not None else [
            {"role": "user", "content": "Can you quote a driveway?"},
            {"role": "assistant", "content": "Yes, what is the address?"},
        ]
        self.lead = lead
        self.appointment = appointment
        self.done = done
        self.cap = cap
        self.existing_task = existing_task
        self.executed = []
        self.fetched = []

    async def fetch(self, sql, *args):
        text = " ".join(sql.split())
        self.fetched.append((text, args))
        if "SELECT m.role, m.content" in text:
            return self.turns
        return []

    async def fetchrow(self, sql, *args):
        if "FROM leads" in sql:
            return self.lead
        return None

    async def fetchval(self, sql, *args):
        text = " ".join(sql.split())
        if "FROM appointments" in text:
            return 1 if self.appointment else None
        if "FROM call_insights" in text and "count(*)" in text:
            return self.cap
        if "FROM call_insights" in text:
            return 1 if self.done else None
        if "FROM tasks" in text:
            return 1 if self.existing_task else None
        return None

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "INSERT 0 1"


TENANT = {"id": "t1", "slug": "pukeko", "name": "Pukeko"}
CALL = {"call_sid": "sip:abc", "tenant_id": "t1", "session_id": "sip:abc",
        "from_number": "+64211234567", "started_at": None, "ended_at": None}


def _run(monkeypatch, pool, reply='{"summary":"Wants a quote","outcome":"call_back","sentiment":"neutral","next_step":"Ring them"}'):
    class Message:
        content = reply

    async def complete(*_a, **_k):
        return Message()

    monkeypatch.setattr(call_insights.db, "pool", lambda: pool)
    monkeypatch.setattr(call_insights.llm, "complete", complete)
    return asyncio.run(call_insights.analyse_call(TENANT, CALL))


def test_analysis_is_persisted_with_the_model_name(monkeypatch):
    pool = FakePool()
    result = _run(monkeypatch, pool)
    assert result["outcome"] == "call_back"
    insert = [row for row in pool.executed if "INSERT INTO call_insights" in row[0]][-1]
    assert insert[1][0] == "sip:abc"
    assert insert[1][4] == "call_back"
    assert insert[1][7]  # model recorded


def test_a_replay_is_a_no_op(monkeypatch):
    pool = FakePool(done=True)
    assert _run(monkeypatch, pool) is None
    assert pool.executed == []


def test_a_call_with_no_conversation_is_skipped(monkeypatch):
    pool = FakePool(turns=[])
    assert _run(monkeypatch, pool) is None
    assert pool.executed == []


def test_the_daily_cap_stops_spending(monkeypatch):
    pool = FakePool(cap=call_insights.DAILY_CAP)
    assert _run(monkeypatch, pool) is None
    assert pool.executed == []


def test_an_unresolved_outcome_creates_one_task_and_never_a_duplicate(monkeypatch):
    lead = {"id": "lead-1", "case_id": "case-1", "name": "Ana", "phone": "+6421"}
    pool = FakePool(lead=lead)
    _run(monkeypatch, pool, reply='{"summary":"Could not help","outcome":"unresolved","sentiment":"negative","next_step":"Ring them"}')
    tasks = [row for row in pool.executed if "INSERT INTO tasks" in row[0]]
    assert len(tasks) == 1
    assert tasks[0][1][4] == "case-1"

    again = FakePool(lead=lead, existing_task=True)
    _run(monkeypatch, again, reply='{"summary":"Could not help","outcome":"unresolved","sentiment":"negative","next_step":"Ring them"}')
    assert [row for row in again.executed if "INSERT INTO tasks" in row[0]] == []


def test_a_booked_appointment_forces_the_booked_outcome(monkeypatch):
    pool = FakePool(appointment=True)
    result = _run(monkeypatch, pool, reply='{"summary":"Booked","outcome":"unresolved","sentiment":"neutral","next_step":""}')
    assert result["outcome"] == "booked"


def test_a_model_failure_still_records_an_honest_row(monkeypatch):
    pool = FakePool()

    async def boom(*_a, **_k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(call_insights.db, "pool", lambda: pool)
    monkeypatch.setattr(call_insights.llm, "complete", boom)
    result = asyncio.run(call_insights.analyse_call(TENANT, CALL))
    assert result["summary"].startswith("Call ended; no automatic summary")
    insert = [row for row in pool.executed if "INSERT INTO call_insights" in row[0]][-1]
    assert insert[1][4] == "unresolved"


def test_sweep_skips_calls_that_already_have_an_insight(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(call_insights.db, "pool", lambda: pool)
    assert asyncio.run(call_insights.sweep()) == 0
    sql, args = pool.fetched[-1]
    # The anti-join is what prevents re-billing the model for the same call.
    assert "LEFT JOIN call_insights" in sql
    assert "i.id IS NULL" in sql
    assert args[0] == 50
