"""Regression tests for PR 2 audit backend correctness fixes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import os
import time

import pytest

from app import (
    email_threading,
    integrations,
    platform_billing,
    portability,
    subscription,
    voicemail_fallback,
)


def test_stripe_verify_signature_accepts_multiple_v1_during_key_rotation():
    secret = "whsec_rotation_secret"
    payload = b'{"id":"evt_1","type":"checkout.session.completed"}'
    ts = int(time.time())
    good = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    # Second v1 is old secret, first v1 is active secret
    header = f"t={ts},v1={good},v1={'0' * 64}"
    assert platform_billing.verify_signature(payload, header, secret, now=ts) is True
    # Reverse order: active secret second
    header_rev = f"t={ts},v1={'0' * 64},v1={good}"
    assert platform_billing.verify_signature(payload, header_rev, secret, now=ts) is True


def test_handle_checkout_mutates_invoice_so_link_checkout_runs(monkeypatch):
    linked = []
    sent_ops = []

    async def fake_issue(**kwargs):
        return {
            "id": 1,
            "number": "TRB-0099",
            "customer_email": "buyer@example.com",
            "customer_name": "Buyer",
            "business_name": "Buyer Co",
            "plan": "Concierge",
            "amount_cents": 25000,
            "currency": "USD",
            "public_token": "tok123",
            "tenant_id": None,
            "emailed_at": "2026-11-22T00:00:00Z",
        }

    async def fake_provision(inv):
        inv["tenant_id"] = "tenant-uuid-99"
        return {"id": "tenant-uuid-99"}

    async def fake_link(tenant_id, session):
        linked.append((tenant_id, session.get("subscription")))

    class FakePool:
        async def fetchrow(self, *args, **kwargs):
            return None

        async def execute(self, *args, **kwargs):
            return None

    monkeypatch.setattr(platform_billing, "issue", fake_issue)
    monkeypatch.setattr(platform_billing, "provision", fake_provision)
    monkeypatch.setattr(subscription, "link_checkout", fake_link)
    monkeypatch.setattr(platform_billing.db, "pool", lambda: FakePool())

    session = {
        "id": "cs_test_1",
        "payment_status": "paid",
        "amount_total": 25000,
        "currency": "usd",
        "customer": "cus_99",
        "subscription": "sub_99",
        "customer_details": {"email": "buyer@example.com", "name": "Buyer"},
    }
    inv = asyncio.run(platform_billing.handle_checkout(session))
    assert inv is not None
    assert inv["tenant_id"] == "tenant-uuid-99"
    assert linked == [("tenant-uuid-99", "sub_99")]


def test_email_thread_key_matches_first_message_and_reply():
    root_id = "<msg1@customer.example>"
    k1 = email_threading.thread_key("alice@example.com", "Quote request", message_id=root_id)
    k2 = email_threading.thread_key("alice@example.com", "Re: Quote request", in_reply_to=root_id, references=[root_id])
    assert k1 == k2


def test_voicemail_sweep_returns_empty_when_spool_dir_blank(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VOICEMAIL_SPOOL_DIR", "")
    get_settings.cache_clear()
    try:
        res = asyncio.run(voicemail_fallback.sweep(""))
        assert res == {"stored": 0, "kept": 0, "duplicate": 0, "skipped": 0, "errors": 0}
    finally:
        get_settings.cache_clear()


def test_subscription_renewal_zero_rates_non_nzd():
    src = inspect.getsource(subscription.on_invoice_paid)
    assert "gst_rate_for" in src
    assert "rate=gst_rate" in src
    assert platform_billing.gst_rate_for("USD", "NZ") == platform_billing.GST_RATE
    assert platform_billing.gst_rate_for("USD", "US") == 0.0
    assert platform_billing.gst_rate_for("NZD", "") == platform_billing.GST_RATE


def test_xero_invoice_sets_inclusive_and_m365_converts_utc():
    assert '"LineAmountTypes": "Inclusive"' in inspect.getsource(integrations._xero)
    assert "astimezone(timezone.utc)" in inspect.getsource(integrations._m365)


def test_portability_uses_skip_locked_and_active_join():
    assert "FOR UPDATE SKIP LOCKED" in inspect.getsource(portability.deliver_pending)
    assert "JOIN tenant_webhooks tw" in inspect.getsource(portability.retry_all)
