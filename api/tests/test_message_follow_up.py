"""Exercise real ingress and real SQL: another message needs another task, not another lead."""
from unittest.mock import AsyncMock

import pytest

from app import automation, enquiries, owner_notifications
from test_case_timeline import real_db, _run  # reuse the disposable-database fixture


@pytest.mark.parametrize("email", ["alice@example.com", ""])
def test_each_new_message_creates_work_and_replays_do_not(real_db, monkeypatch, email):
    tenant_id = _run(real_db.fetchval(
        "INSERT INTO tenants(slug,name,public_key,default_country_code) "
        "VALUES('follow-up','Follow Up','pk-follow-up','64') RETURNING id"))
    tenant = dict(_run(real_db.fetchrow("SELECT * FROM tenants WHERE id=$1", tenant_id)))
    monkeypatch.setattr(owner_notifications, "queue", AsyncMock())
    monkeypatch.setattr(automation.events, "emit", lambda *a, **kw: None)
    monkeypatch.setattr(automation.events, "queue_twenty", AsyncMock())
    monkeypatch.setattr(automation, "lead_followup", AsyncMock())
    async def capture(message):
        return await enquiries.capture(tenant, "chat", "conversation-1", message,
                                       email=email)
    first = _run(capture("Can you give me a quote?"))
    second = _run(capture("I have another question"))
    replay = _run(capture("I have another question"))
    assert first["id"] == second["id"] == replay["id"]
    assert _run(real_db.fetchval("SELECT count(*) FROM tasks WHERE kind='follow_up'")) == 2
    assert _run(real_db.fetchval("SELECT count(*) FROM case_events")) == (2 if email else 0)
