"""N8 Tenant Online Payments tests:
- Stripe Connect disabled cleanly until STRIPE_SECRET_KEY + STRIPE_CONNECT_CLIENT_ID are configured
- Deposit -> follow-up balance invoice generator works regardless of Stripe
- Checkout session creation & signed Connect webhook mark invoice deposit_paid / paid
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import pathlib
import time

import asyncpg
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, owner_auth, tenant_payments, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
    db._pool = pool
    return pool


def run(fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


@needs_db
def test_n8_stripe_connect_disabled_by_default_and_deposit_balance_flow(monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "", raising=False)
    monkeypatch.setattr(get_settings(), "stripe_connect_client_id", "", raising=False)

    async def _go(pool):
        t = await tenants.create("Pay Co", "https://payco.example", "pay-co")
        inv = await owner_auth.make_invite(t["id"], "owner@payco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        lead_id = await pool.fetchval(
            "INSERT INTO leads(tenant_id, name, email) VALUES($1, 'Buyer', 'b@payco.test') RETURNING id",
            t["id"],
        )
        q_id = await pool.fetchval(
            "INSERT INTO quotations(tenant_id, lead_id, title, currency, status, lines, contact, "
            "tax_basis_points, subtotal_cents, tax_cents, total_cents) "
            "VALUES($1, $2, 'Roof', 'NZD', 'accepted', '[]'::jsonb, '{}'::jsonb, 1500, 86957, 13043, 100000) RETURNING id",
            t["id"], lead_id,
        )
        inv_id = await pool.fetchval(
            "INSERT INTO invoices(tenant_id, quotation_id, number, kind, status, subtotal_cents, total_cents, "
            "due_cents, deposit_cents, balance_cents, currency, public_token) "
            "VALUES($1, $2, 'INV-100', 'deposit', 'issued', 100000, 100000, 30000, 30000, 70000, 'NZD', 'tok-inv-100') RETURNING id",
            t["id"], q_id,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Disabled by default when Stripe Connect keys are unset
            st = await client.get("/owner/payments/connect", headers=headers)
            assert st.status_code == 200 and st.json()["platform_configured"] is False
            assert (await client.post("/owner/payments/connect/start", headers=headers)).status_code == 409
            assert (await client.post(f"/owner/invoices/{inv_id}/checkout", headers=headers, json={"kind": "deposit"})).status_code == 409

            # 2. Follow-up balance invoice generator works even without Stripe
            bal = await client.post(f"/owner/invoices/{inv_id}/balance-invoice", headers=headers)
            assert bal.status_code == 201
            assert bal.json()["number"] == "INV-100-BAL"
            assert bal.json()["due_cents"] == 70000

            # 3. Express onboarding via Account Links needs ONLY STRIPE_SECRET_KEY (no Connect client_id)
            monkeypatch.setattr(get_settings(), "stripe_secret_key", "stripe-test-mode", raising=False)
            monkeypatch.setattr(get_settings(), "stripe_connect_client_id", "", raising=False)
            monkeypatch.setattr(get_settings(), "stripe_connect_webhook_secret", "connect-hook-secret", raising=False)

            async def fake_http(method, url, **kw):
                if url.endswith("/v1/accounts") and method == "POST":
                    return httpx.Response(200, json={"id": "acct_express_1"})
                if url.endswith("/v1/account_links") and method == "POST":
                    return httpx.Response(200, json={"url": "https://connect.stripe.com/setup/e/acct_express_1"})
                if url.endswith("/v1/accounts/acct_express_1") and method == "GET":
                    return httpx.Response(200, json={"id": "acct_express_1", "charges_enabled": True, "payouts_enabled": True})
                return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})
            monkeypatch.setattr(tenant_payments, "http", fake_http)

            st_on = await client.get("/owner/payments/connect", headers=headers)
            assert st_on.status_code == 200 and st_on.json()["platform_configured"] is True

            started = await client.post("/owner/payments/connect/start", headers=headers)
            assert started.status_code == 200
            assert started.json()["stripe_account_id"] == "acct_express_1"
            assert started.json()["authorize_url"].startswith("https://connect.stripe.com/")

            synced = await client.post("/owner/payments/connect/sync", headers=headers)
            assert synced.status_code == 200
            assert synced.json()["connected"] is True and synced.json()["charges_enabled"] is True

            co = await client.post(f"/owner/invoices/{inv_id}/checkout", headers=headers, json={"kind": "deposit"})
            assert co.status_code == 200 and co.json()["amount_cents"] == 30000

            # Simulate signed Stripe Connect webhook for account.updated & checkout.session.completed
            acct_payload = json.dumps({
                "type": "account.updated",
                "data": {"object": {"id": "acct_express_1", "charges_enabled": True, "payouts_enabled": True}},
            }).encode("utf-8")
            ts = str(int(time.time()))
            sig_a = hmac.new(b"connect-hook-secret", f"{ts}.".encode() + acct_payload, hashlib.sha256).hexdigest()
            wh_a = await client.post("/webhooks/stripe-connect", content=acct_payload, headers={"stripe-signature": f"t={ts},v1={sig_a}"})
            assert wh_a.status_code == 200

            payload = json.dumps({
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_test_1", "metadata": {"invoice_id": str(inv_id), "payment_kind": "deposit"}}},
            }).encode("utf-8")
            sig = hmac.new(b"connect-hook-secret", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
            wh = await client.post("/webhooks/stripe-connect", content=payload, headers={"stripe-signature": f"t={ts},v1={sig}"})
            assert wh.status_code == 200
            assert await pool.fetchval("SELECT status FROM invoices WHERE id=$1", inv_id) == "deposit_paid"
    run(_go)
