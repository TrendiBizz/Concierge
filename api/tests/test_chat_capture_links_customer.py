"""A chat visitor who gives an email must become a customer, not just a lead row.

Before this, the lead was written with no case, so the same person emailing next week arrived as a
stranger with a second history. The fix reconciles the customer first and stamps the case onto the
lead.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import tools


def test_chat_lead_is_linked_to_a_customer(monkeypatch):
    tenant = {"id": "business-a", "name": "Test", "sms_enabled": True}
    lead = {"id": 7, "tenant_id": "business-a", "conversation_id": None, "name": "Hana",
            "phone": "", "email": "hana@acme.co.nz", "channel": "chat", "message": "hello",
            "consent_contact": True, "consent_marketing": False}
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value=lead), execute=AsyncMock())
    monkeypatch.setattr(tools.db, "pool", lambda: pool)
    monkeypatch.setattr(tools, "get_settings", lambda: SimpleNamespace(default_country_code="64"))
    reconcile = AsyncMock(return_value={"id": "case-1", "case_key": "email:hana@acme.co.nz"})
    monkeypatch.setattr(tools.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(tools.casetimeline, "tenant_country_code", lambda t: "64")
    monkeypatch.setattr(tools.automation, "on_lead_created", AsyncMock())

    result = asyncio.run(tools.run_tool(tenant, "capture_lead", {
        "name": "Hana", "email": "hana@acme.co.nz", "message": "hello",
        "consent_to_contact": True}, {"channel": "chat", "utm": {}}))

    assert result["ok"]
    assert reconcile.await_count == 1, "the lead was saved without reconciling a customer"
    assert reconcile.await_args.kwargs["source"] == "chat"
    stamped = [c.args for c in pool.execute.await_args_list if "UPDATE leads SET case_id" in c.args[0]]
    assert stamped and stamped[-1][2] == "case-1", "the lead was not stamped with the customer"
