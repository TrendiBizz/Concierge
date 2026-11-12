"""Our own mail routed back into the platform must never become an enquiry (the 2026-11-13 loop)."""
import asyncio
import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from app import cloudflare_inbound, mailer

SECRET = "s" * 40
OWN = "Trendi Concierge <alerts@example.com>"


def _settings(**extra):
    base = {"inbound_cloudflare_enabled": True, "inbound_cloudflare_secret": SECRET, "smtp_from": OWN}
    base.update(extra)
    return SimpleNamespace(**base)


def _raw(marker):
    head = "From: alerts@example.com\r\nTo: admin@example.com\r\nSubject: Email enquiry\r\n"
    if marker:
        head += "X-Concierge-Mail: 1\r\nAuto-Submitted: auto-generated\r\n"
    return (head + "\r\nbody\r\n").encode()


def test_marker_header_means_our_own_mail(monkeypatch):
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: _settings())
    assert cloudflare_inbound.is_own_mail("anyone@example.com", _raw(True)) is True


def test_a_person_mailing_from_the_same_address_is_not_dropped_when_raw_is_present(monkeypatch):
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: _settings())
    assert cloudflare_inbound.is_own_mail("alerts@example.com", _raw(False)) is False


def test_without_raw_the_sender_address_is_the_fallback(monkeypatch):
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: _settings())
    assert cloudflare_inbound.is_own_mail("alerts@example.com", None) is True
    assert cloudflare_inbound.is_own_mail("Trendi <ALERTS@Example.com>", None) is True
    assert cloudflare_inbound.is_own_mail("customer@example.com", None) is False


def test_unparsable_raw_and_missing_setting_are_safe(monkeypatch):
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: _settings())
    assert cloudflare_inbound.is_own_mail("c@example.com", b"\xff\xfe not an email") is False
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: SimpleNamespace())
    assert cloudflare_inbound.is_own_mail("c@example.com", None) is False


def test_every_outgoing_message_is_marked(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

        def quit(self):
            pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer, "get_settings", lambda: SimpleNamespace(
        smtp_from="alerts@example.com", smtp_security="none", smtp_host="h", smtp_port=25,
        smtp_user="", smtp_password=""))
    mailer._send_sync("owner@example.com", "Hi", "body")
    assert sent[0]["X-Concierge-Mail"] == "1"
    assert sent[0]["Auto-Submitted"] == "auto-generated"


def _request(payload):
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    headers = {b"x-concierge-timestamp": stamp.encode(),
               b"x-concierge-signature": cloudflare_inbound.signature(SECRET, stamp, body).encode(),
               b"content-type": b"application/json"}
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": list(headers.items()), "client": ("1.2.3.4", 1)}, receive)


def test_the_handler_drops_our_own_mail_before_it_can_become_a_draft(monkeypatch):
    class Pool:
        executed = []

        async def fetchrow(self, query, *args):
            return {"tenant_id": "tenant-1"}

        async def fetchval(self, query, *args):
            raise AssertionError("must not reach the flood counters or create a draft")

        async def execute(self, query, *args):
            self.executed.append(query)

    pool = Pool()
    monkeypatch.setattr(cloudflare_inbound, "get_settings", lambda: _settings())
    monkeypatch.setattr(cloudflare_inbound.db, "pool", lambda: pool)
    audit = AsyncMock()
    monkeypatch.setattr(cloudflare_inbound.inbound_policy, "audit", audit)
    payload = {"message_id": "<m@example.com>", "recipient": "reply-abc@example.com",
               "sender": "alerts@example.com", "subject": "Email enquiry for Trendi Concierge",
               "text": "A new enquiry", "raw_b64": base64.b64encode(_raw(True)).decode()}
    result = asyncio.run(cloudflare_inbound.handle(_request(payload)))
    assert result == {"accepted": True, "dropped": "own_mail"}
    assert audit.await_args.args[2] == "inbound_loop_guard"
    assert pool.executed == []
