from datetime import datetime

from app.sales import daily_is_due, daily_text

TENANT = {"name": "Acme"}


def s(**kw):
    base = {"new_leads": 0, "overdue_todos": 0, "leads_waiting": 0}
    return {**base, **kw}


def test_due_only_between_7_and_10_local():
    assert not daily_is_due(datetime(2026, 11, 17, 6, 59))
    assert daily_is_due(datetime(2026, 11, 17, 7, 0)) and daily_is_due(datetime(2026, 11, 17, 9, 59))
    assert not daily_is_due(datetime(2026, 11, 17, 10, 0))


def test_a_quiet_day_sends_nothing():
    assert daily_text(TENANT, s()) is None
    assert daily_text(TENANT, s(leads_waiting=None)) is None


def test_a_busy_day_names_what_needs_the_owner():
    subject, body = daily_text(TENANT, s(new_leads=2, leads_waiting=1, overdue_todos=3))
    assert "1 waiting for a reply" in subject
    assert "Waiting for a reply: 1" in body and "To-dos overdue: 3" in body
    assert "Nothing is sent to your customers" in body
