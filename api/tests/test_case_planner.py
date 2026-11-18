"""The planner proposes one plan. Concierge keeps it or drops it. Nothing is sent."""
from app import case_planner


def test_a_valid_plan_becomes_a_todo_and_is_not_executed():
    reply = '{"confidence": 0.4, "actions": [{"op": "prepare_reply", "params": {"body": "Thanks"}}]}'
    note = case_planner.decide(reply)
    assert note is not None
    assert note["title"] == "Planner suggestion"
    assert "prepare_reply" in note["notes"]
    assert "not" in note["notes"] or "shadow" in note["notes"]
    assert "Thanks" not in note["notes"]


def test_a_plan_that_names_a_tenant_is_dropped():
    reply = '{"confidence": 0.9, "tenant_id": "other-business", "actions": [{"op": "create_task"}]}'
    assert case_planner.decide(reply) is None


def test_one_call_and_a_missing_claude_does_not_invent_a_plan(monkeypatch):
    monkeypatch.setattr(case_planner, "get_settings", lambda: type("S", (), {"case_planner": "claude"})())
    calls = []

    def run(prompt):
        calls.append(prompt)
        return '{"confidence": 0.2, "actions": [{"op": "create_task", "params": {}}]}'

    note = case_planner.note_for({"channel": "email", "message": "Can you quote the deck?"}, run=run)
    assert len(calls) == 1
    assert "quote the deck" in calls[0]
    assert note is not None
    assert "create_task" in note["notes"]

    monkeypatch.setattr(case_planner.shutil, "which", lambda _name: None)
    assert case_planner.note_for({"message": "hello"}) is None
