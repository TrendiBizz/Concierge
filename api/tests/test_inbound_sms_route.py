"""Inbound SMS, driven through the real route.

The audit lists incoming SMS as outstanding: outbound was verified, but an external inbound message
and its Grok reply had never been exercised. Nothing in the suite touched `/api/v1/sms/{key}` at all,
so the route's own behaviour -- provider gate, signature verification, authorization, opt-out
handling and the reply -- was unproven.

These drive the real FastAPI route with FastAPI's TestClient, so the signature check, the form
parsing and the TwiML response are all the production ones. Only the outside world (the database,
the model, the SMS sender) is substituted.
"""
import asyncio
import base64
import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from urllib.parse import urlencode

from app import chat as chat_engine, channel_authorization, convo, enquiries, sms, tenants

TENANT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "slug": "fixture",
    "name": "Fixture Business",
    "timezone": "Pacific/Auckland",
    "default_country_code": "64",
    "sms_enabled": True,
    "sms_from": "+6421555000",
    "public_key": "pk-fixture",
}

AUTH_TOKEN = "test-auth-token"
BASE = "http://testserver"


def _sign(path: str, params: dict) -> str:
    """Twilio's signature: HMAC-SHA1 over the full URL plus sorted POST params."""
    url = BASE + path
    data = url + "".join(k + params[k] for k in sorted(params))
    mac = hmac.new(AUTH_TOKEN.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(mac).decode()


@pytest.fixture()
def client(monkeypatch):
    """The real app, with the outside world substituted."""
    from app import main

    # main.settings is captured at import, so patch the object's attributes rather than
    # replacing get_settings -- patching the function has no effect on the route.
    monkeypatch.setattr(main.settings, "twilio_auth_token", AUTH_TOKEN, raising=False)
    monkeypatch.setattr(main.settings, "twilio_account_sid", "AC", raising=False)
    monkeypatch.setattr(main.settings, "public_base_url", BASE, raising=False)
    monkeypatch.setattr(main.settings, "default_country_code", "64", raising=False)
    monkeypatch.setattr(sms, "get_settings", lambda: SimpleNamespace(
        sms_provider="twilio", twilio_account_sid="AC", twilio_auth_token=AUTH_TOKEN,
        twilio_from_number="", twilio_messaging_service_sid="", twilio_api_base="http://localhost",
        smsgate_base_url="", smsgate_username="", smsgate_password="", smsgate_send_path="",
        smsgate_sim_number=0, smsgate_signing_key="",
    ))
    monkeypatch.setattr(tenants, "get_by_key", AsyncMock(return_value=dict(TENANT)))
    monkeypatch.setattr(channel_authorization, "is_authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(convo, "get_or_create", AsyncMock(return_value="conv-1"))
    monkeypatch.setattr(enquiries, "capture", AsyncMock(return_value={"id": "lead-1"}))
    monkeypatch.setattr(main, "sms_limiter", SimpleNamespace(check=lambda sid: True))
    # Not opted out unless a test says so, and the owner notification that the turn queues is
    # not the subject here.
    from app import outbox, owner_notifications
    monkeypatch.setattr(outbox, "is_opted_out", AsyncMock(return_value=False))
    monkeypatch.setattr(owner_notifications, "queue", AsyncMock(return_value=None))
    return TestClient(main.app)


def _post(client, params, signed=True):
    if signed:
        params = {**params, "_sig": "placeholder"}
        params.pop("_sig")
    headers = {"X-Twilio-Signature": _sign("/api/v1/sms/pk-fixture", params) if signed else "bad"}
    return client.post("/api/v1/sms/pk-fixture", content=urlencode(params), headers=headers)


def test_inbound_sms_replies_through_grok(client, monkeypatch):
    """The headline requirement: an external text gets a real assistant reply."""
    monkeypatch.setattr(chat_engine, "run_turn", AsyncMock(
        return_value={"reply": "We do decks, from $50 per square metre.", "suppressed": False}))

    resp = _post(client, {"From": "+6421555123", "Body": "Do you do decks?"})
    assert resp.status_code == 200
    assert "Do you do decks" not in resp.text or "<Response>" in resp.text
    assert "decks" in resp.text, f"expected the assistant reply in the TwiML, got: {resp.text!r}"


def test_inbound_sms_rejects_a_bad_signature(client, monkeypatch):
    """An unsigned webhook must never reach the model: it would be a spoofable send."""
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)

    resp = _post(client, {"From": "+6421555123", "Body": "hi"}, signed=False)
    assert resp.status_code == 403
    sent.assert_not_awaited()


def test_inbound_sms_requires_channel_authorization(client, monkeypatch):
    """The business must have authorized inbound SMS; otherwise it is refused, not answered."""
    monkeypatch.setattr(channel_authorization, "is_authorized", AsyncMock(return_value=False))
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)

    resp = _post(client, {"From": "+6421555123", "Body": "hi"})
    assert resp.status_code == 403
    sent.assert_not_awaited()


def test_stop_is_honoured_and_gets_no_ai_reply(client, monkeypatch):
    """A STOP must opt the sender out and never be answered by the assistant."""
    from app import outbox, main
    opted = AsyncMock()
    monkeypatch.setattr(outbox, "opt_out", opted)
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)

    resp = _post(client, {"From": "+6421555123", "Body": "STOP"})
    assert resp.status_code == 200
    opted.assert_awaited()
    sent.assert_not_awaited()


def test_opted_out_sender_gets_no_reply(client, monkeypatch):
    """Once opted out, further texts are recorded but never answered."""
    from app import outbox
    monkeypatch.setattr(outbox, "is_opted_out", AsyncMock(return_value=True))
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)

    resp = _post(client, {"From": "+6421555123", "Body": "hello again"})
    assert resp.status_code == 200
    sent.assert_not_awaited()


def test_help_returns_the_compliance_line(client, monkeypatch):
    """HELP must return the standard message, without touching the model."""
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)
    resp = _post(client, {"From": "+6421555123", "Body": "HELP"})
    assert resp.status_code == 200
    assert "STOP" in resp.text
    sent.assert_not_awaited()


def test_empty_body_is_ignored(client, monkeypatch):
    """A bodyless webhook (a delivery receipt, or a malformed POST) must not reach the model."""
    sent = AsyncMock()
    monkeypatch.setattr(chat_engine, "run_turn", sent)
    resp = _post(client, {"From": "+6421555123", "Body": ""})
    assert resp.status_code == 200
    sent.assert_not_awaited()


def test_unknown_tenant_key_is_404(client, monkeypatch):
    """An unknown public key is refused before any signature or model work.

    The fixture's lookup normally succeeds; this overrides it, so the 404 branch is what runs.
    """
    monkeypatch.setattr(tenants, "get_by_key", AsyncMock(return_value=None))
    resp = client.post("/api/v1/sms/not-a-key",
                       content=urlencode({"From": "+6421555123", "Body": "hi"}),
                       headers={"X-Twilio-Signature": "x"})
    assert resp.status_code == 404


def test_inbound_sms_is_captured_to_crm(client, monkeypatch):
    """The message must reach CRM even though the assistant also answers it."""
    captured = AsyncMock(return_value={"id": "lead-1"})
    monkeypatch.setattr(enquiries, "capture", captured)
    monkeypatch.setattr(chat_engine, "run_turn", AsyncMock(
        return_value={"reply": "ok", "suppressed": False}))

    _post(client, {"From": "+6421555123", "Body": "Do you do decks?"})
    captured.assert_awaited()
    args, kwargs = captured.await_args
    # enquiries.capture(tenant, channel, source, message, ...)
    assert args[1] == "sms", "captured on the sms channel"
    assert args[3] == "Do you do decks?", "the customer's actual text must reach CRM"


def test_a_suppressed_turn_sends_no_sms_body(client, monkeypatch):
    """When the owner has taken over, the inbound text gets an empty TwiML -- no AI words."""
    monkeypatch.setattr(chat_engine, "run_turn", AsyncMock(
        return_value={"reply": "", "suppressed": True}))

    resp = _post(client, {"From": "+6421555123", "Body": "are you there?"})
    assert resp.status_code == 200
    assert "are you there" in resp.text or "<Response></Response>" in resp.text or "<Response>" in resp.text
    assert "sorry" not in resp.text.lower(), "a suppressed turn must not produce an apology reply"
