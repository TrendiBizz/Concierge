"""Whatever a customer writes is captured on every channel, not only their contact details."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import enquiries, tools

TENANT = {"id": uuid.uuid4(), "slug": "acme", "name": "Acme", "default_country_code": "64"}


def test_a_chat_message_is_mined_for_every_detail_it_contains(monkeypatch):
    seen = {}

    async def fake_reconcile(tenant_id, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(enquiries.casetimeline, "reconcile", fake_reconcile)
    with __import__("pytest").raises(RuntimeError):
        asyncio.run(enquiries.capture(
            TENANT, "chat", "src-1",
            "Hi it's Sarah from Acme Construction, can you call me on 021 555 1234"))
    assert seen["name"] == "Sarah", "the visitor's name was not captured from the message"
    assert seen["company"] == "Acme Construction"
    assert seen["phone"] == "+64215551234"


def test_details_the_channel_already_supplied_are_not_overwritten(monkeypatch):
    seen = {}

    async def fake_reconcile(tenant_id, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(enquiries.casetimeline, "reconcile", fake_reconcile)
    with __import__("pytest").raises(RuntimeError):
        asyncio.run(enquiries.capture(
            TENANT, "email", "src-2", "my name is Not This Name",
            email="real@customer.co.nz", name="Real Name"))
    assert seen["name"] == "Real Name"
    assert seen["email"] == "real@customer.co.nz"


def test_the_assistant_can_save_a_named_enquirer_with_no_contact_details(monkeypatch):
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "id": 1, "tenant_id": TENANT["id"], "conversation_id": None, "name": "Sarah",
        "company": "", "email": "", "phone": "", "channel": "chat", "message": "quote please",
        "consent_contact": False, "consent_marketing": False}), execute=AsyncMock())
    monkeypatch.setattr(tools.db, "pool", lambda: pool)
    monkeypatch.setattr(tools, "get_settings", lambda: SimpleNamespace(default_country_code="64"))
    monkeypatch.setattr(tools.casetimeline, "reconcile", AsyncMock(return_value=None))
    monkeypatch.setattr(tools.casetimeline, "tenant_country_code", lambda t: "64")
    monkeypatch.setattr(tools.automation, "on_lead_created", AsyncMock())

    result = asyncio.run(tools.run_tool(TENANT, "capture_lead", {"name": "Sarah"},
                                        {"channel": "chat", "utm": {}}))
    assert result["ok"], "a named enquirer was refused because they gave no phone or email"


def test_the_company_reaches_the_customer_record(monkeypatch):
    """A company named in the message must survive into the customer, not just the lead."""
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "id": 9, "tenant_id": TENANT["id"], "conversation_id": None, "name": "Sarah",
        "company": "", "email": "", "phone": "", "channel": "chat", "message": "x",
        "consent_contact": False, "consent_marketing": False}), execute=AsyncMock())
    monkeypatch.setattr(tools.db, "pool", lambda: pool)
    monkeypatch.setattr(tools, "get_settings", lambda: SimpleNamespace(default_country_code="64"))
    reconcile = AsyncMock(return_value={"id": "case-9"})
    monkeypatch.setattr(tools.casetimeline, "reconcile", reconcile)
    monkeypatch.setattr(tools.casetimeline, "tenant_country_code", lambda t: "64")
    monkeypatch.setattr(tools.automation, "on_lead_created", AsyncMock())

    asyncio.run(tools.run_tool(
        TENANT, "capture_lead", {"message": "quote please"},
        {"channel": "chat", "utm": {}, "last_message": "it's Sarah from Acme Construction"}))
    assert reconcile.await_args.kwargs["company"] == "Acme Construction"


def test_an_email_signature_names_the_customer_from_the_shared_funnel(monkeypatch):
    """Any path that lands an email body must read the signature, not just the inbound-email handler."""
    seen = {}

    async def fake_reconcile(tenant_id, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(enquiries.casetimeline, "reconcile", fake_reconcile)
    body = ("Hi, we have a two-storey house that needs recladding.\n\n"
            "Best regards,\n\nSarah Whitfield\nAcme Construction\n021 555 7001")
    with __import__("pytest").raises(RuntimeError):
        asyncio.run(enquiries.capture(TENANT, "email", "src-9", body,
                                      email="sarah@acme.example.nz"))
    assert seen["name"] == "Sarah Whitfield", "the signature name was not captured"
    assert seen["company"] == "Acme Construction", "the signature company was not captured"
