"""N1: Stripe subscription lifecycle (renewal, dunning, cancel, refund) against a real Postgres."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest

from app import db, main as app_main, owner_auth, platform_billing, subscription
from app.config import get_settings

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


def event(kind: str, obj: dict, eid: str | None = None) -> dict:
    return {"id": eid or "evt_" + uuid.uuid4().hex[:10], "type": kind, "data": {"object": obj}}


async def _tenant(pool, slug="acme", **cols):
    tid = await pool.fetchval(
        "INSERT INTO tenants(slug,name,public_key,stripe_customer_id,stripe_subscription_id,billing_status) "
        "VALUES($1,$2,$3,'cus_1','sub_1','active') RETURNING id", slug, slug.title(), "pk_" + slug)
    return tid


def run(coro_fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await coro_fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


@needs_db
def test_payment_failed_starts_grace_and_sweep_pauses_only_after_it_ends():
    async def go(pool):
        tid = await _tenant(pool)
        await subscription.handle_event(event("invoice.payment_failed", {"id": "in_1", "customer": "cus_1", "attempt_count": 1}))
        row = await pool.fetchrow("SELECT billing_status,billing_grace_until,paused_at FROM tenants WHERE id=$1", tid)
        assert row["billing_status"] == "past_due" and row["paused_at"] is None
        assert row["billing_grace_until"] > datetime.now(timezone.utc) + timedelta(days=6)
        assert await subscription.sweep() == 0          # still inside the grace period
        await pool.execute("UPDATE tenants SET billing_grace_until=now()-interval '1 hour' WHERE id=$1", tid)
        assert await subscription.sweep() == 1
        row = await pool.fetchrow("SELECT paused_at,paused_by FROM tenants WHERE id=$1", tid)
        assert row["paused_at"] is not None and row["paused_by"] == "billing"
        assert await subscription.sweep() == 0          # idempotent
    run(go)


@needs_db
def test_a_second_failure_does_not_extend_the_grace_period():
    async def go(pool):
        tid = await _tenant(pool)
        await subscription.handle_event(event("invoice.payment_failed", {"id": "in_1", "customer": "cus_1"}))
        first = await pool.fetchval("SELECT billing_grace_until FROM tenants WHERE id=$1", tid)
        await subscription.handle_event(event("invoice.payment_failed", {"id": "in_2", "customer": "cus_1"}))
        assert await pool.fetchval("SELECT billing_grace_until FROM tenants WHERE id=$1", tid) == first
    run(go)


@needs_db
def test_renewal_payment_clears_dunning_resumes_billing_pause_and_issues_one_invoice():
    async def go(pool):
        tid = await _tenant(pool)
        await pool.execute("UPDATE tenants SET billing_status='past_due', notify_email='o@acme.test' WHERE id=$1", tid)
        await subscription.suspend(dict(await pool.fetchrow("SELECT * FROM tenants WHERE id=$1", tid)), "overdue")
        paid = {"id": "in_9", "customer": "cus_1", "subscription": "sub_1", "amount_paid": 28750,
                "currency": "nzd", "billing_reason": "subscription_cycle", "customer_email": "o@acme.test"}
        ev = event("invoice.paid", paid, "evt_same")
        assert await subscription.handle_event(ev) is True
        assert await subscription.handle_event(ev) is False       # Stripe retry is a no-op
        row = await pool.fetchrow("SELECT billing_status,billing_grace_until,paused_at FROM tenants WHERE id=$1", tid)
        assert row["billing_status"] == "active" and row["billing_grace_until"] is None and row["paused_at"] is None
        invoices = await pool.fetch("SELECT * FROM platform_invoices WHERE tenant_id=$1", tid)
        assert len(invoices) == 1 and invoices[0]["amount_cents"] == 28750 and invoices[0]["gst_cents"] == 3750
        # A replay under a *new* event id still must not double-invoice the same Stripe invoice.
        await subscription.handle_event(event("invoice.paid", paid))
        assert await pool.fetchval("SELECT count(*) FROM platform_invoices WHERE tenant_id=$1", tid) == 1
    run(go)


@needs_db
def test_owner_chosen_pause_survives_payment():
    async def go(pool):
        tid = await _tenant(pool)
        await pool.execute("UPDATE tenants SET paused_at=now(), paused_by='owner@acme.test' WHERE id=$1", tid)
        await subscription.handle_event(event("invoice.paid", {"id": "in_1", "customer": "cus_1", "amount_paid": 0}))
        assert await pool.fetchval("SELECT paused_at IS NOT NULL FROM tenants WHERE id=$1", tid)
    run(go)


@needs_db
def test_cancel_at_period_end_keeps_access_then_deletion_pauses():
    async def go(pool):
        tid = await _tenant(pool)
        end = int((datetime.now(timezone.utc) + timedelta(days=10)).timestamp())
        await subscription.handle_event(event("customer.subscription.updated", {
            "id": "sub_1", "customer": "cus_1", "status": "active", "cancel_at_period_end": True,
            "current_period_end": end}))
        row = await pool.fetchrow("SELECT * FROM tenants WHERE id=$1", tid)
        assert row["billing_cancel_at_period_end"] and row["paused_at"] is None
        assert int(row["billing_period_end"].timestamp()) == end
        await subscription.handle_event(event("customer.subscription.deleted", {"id": "sub_1", "customer": "cus_1"}))
        row = await pool.fetchrow("SELECT billing_status,paused_by FROM tenants WHERE id=$1", tid)
        assert row["billing_status"] == "canceled" and row["paused_by"] == "billing"
    run(go)


@needs_db
def test_unknown_customer_and_unhandled_events_are_ignored_safely():
    async def go(pool):
        await subscription.handle_event(event("invoice.payment_failed", {"customer": "cus_none"}))
        assert await subscription.handle_event(event("customer.created", {})) is False
    run(go)


@needs_db
def test_bank_transfer_tenants_are_never_auto_suspended():
    async def go(pool):
        tid = await pool.fetchval("INSERT INTO tenants(slug,name,public_key) VALUES('bank','Bank','pk_b') RETURNING id")
        assert await subscription.sweep() == 0
        assert await pool.fetchval("SELECT paused_at IS NULL FROM tenants WHERE id=$1", tid)
    run(go)


@needs_db
def test_refund_marks_the_invoice_and_is_recorded():
    async def go(pool):
        tid = await _tenant(pool)
        await platform_billing.issue(email="o@acme.test", name="O", business="Acme", plan="Concierge",
                                     amount_cents=28750, tenant_id=tid)
        await subscription.handle_event(event("charge.refunded", {
            "id": "ch_1", "customer": "cus_1", "amount": 28750, "amount_refunded": 28750, "currency": "nzd"}))
        assert await pool.fetchval("SELECT status FROM platform_invoices WHERE tenant_id=$1", tid) == "refunded"
        assert await pool.fetchval("SELECT count(*) FROM billing_events WHERE kind='refund'") == 1
    run(go)


@needs_db
def test_a_failing_handler_releases_the_event_so_stripe_can_retry(monkeypatch):
    async def go(pool):
        await _tenant(pool)
        async def boom(obj, eid=""):
            raise RuntimeError("db hiccup")
        monkeypatch.setitem(subscription.HANDLERS, "invoice.payment_failed", boom)
        with pytest.raises(RuntimeError):
            await subscription.handle_event(event("invoice.payment_failed", {"customer": "cus_1"}, "evt_x"))
        assert await pool.fetchval("SELECT count(*) FROM stripe_events WHERE event_id='evt_x'") == 0
    run(go)


@needs_db
def test_webhook_route_dispatches_lifecycle_events(monkeypatch):
    async def go(pool):
        tid = await _tenant(pool)
        monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_n1", raising=False)
        body = json.dumps(event("invoice.payment_failed", {"id": "in_7", "customer": "cus_1"})).encode()
        import hashlib, hmac, time
        stamp = int(time.time())
        sig = hmac.new(b"whsec_n1", f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://t") as c:
            r = await c.post("/webhooks/stripe", content=body, headers={"Stripe-Signature": f"t={stamp},v1={sig}"})
            assert r.status_code == 200, r.text
        assert await pool.fetchval("SELECT billing_status FROM tenants WHERE id=$1", tid) == "past_due"
    run(go)


@needs_db
def test_billing_status_and_portal_endpoints(monkeypatch):
    async def go(pool):
        tid = await _tenant(pool)
        app_main.app.dependency_overrides[owner_auth.current_user] = lambda: {
            "id": uuid.uuid4(), "tenant_id": tid, "role": "owner", "email": "o@acme.test", "slug": "acme", "name": "Acme"}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://t") as c:
                s = (await c.get("/owner/billing/status")).json()
                assert s["status"] == "active" and s["portal_available"] is False
                assert (await c.post("/owner/billing/portal")).status_code == 503   # needs the Stripe secret key
                monkeypatch.setattr(get_settings(), "stripe_secret_key", "sk_test_x", raising=False)
                assert (await c.get("/owner/billing/status")).json()["portal_available"] is True
                app_main.app.dependency_overrides[owner_auth.current_user] = lambda: {
                    "id": uuid.uuid4(), "tenant_id": tid, "role": "staff", "email": "s@acme.test", "slug": "acme", "name": "Acme"}
                assert (await c.get("/owner/billing/status")).status_code == 403
        finally:
            app_main.app.dependency_overrides.clear()
    run(go)


def test_pure_helpers():
    assert subscription.normalise_status("past_due") == "past_due"
    assert subscription.normalise_status("") == "none"
    d = subscription.grace_deadline(datetime(2026, 1, 1, tzinfo=timezone.utc), 7)
    assert d == datetime(2026, 1, 8, tzinfo=timezone.utc)
    assert subscription.period_end({"items": {"data": [{"current_period_end": 1800000000}]}}) is not None
    assert subscription.period_end({}) is None
