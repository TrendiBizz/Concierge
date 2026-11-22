"""N8 Tenant Online Payments on Quotes & Invoices (Stripe Connect Standard + Deposit/Balance flow).

Bank transfer remains the zero-fee default. Stripe Connect ships DISABLED until
`STRIPE_SECRET_KEY` and `STRIPE_CONNECT_CLIENT_ID` are configured on the VPS.
The deposit -> follow-up balance invoice generator works for both bank transfer and card payments.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import db, owner_auth
from .config import get_settings

owner_router = APIRouter(prefix="/owner/payments", tags=["tenant-payments"])
invoice_router = APIRouter(prefix="/owner/invoices", tags=["tenant-payments"])
webhook_router = APIRouter(tags=["tenant-payments"])


def platform_configured() -> bool:
    s = get_settings()
    return bool((s.stripe_secret_key or "").strip() and (s.stripe_connect_client_id or "").strip())


async def http(method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.request(method, url, **kwargs)


@owner_router.get("/connect")
async def connect_status(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "SELECT stripe_account_id, charges_enabled, payouts_enabled, status, connected_at "
        "FROM tenant_stripe_connect WHERE tenant_id=$1",
        user["tenant_id"],
    )
    enabled = platform_configured()
    return {
        "platform_configured": enabled,
        "unavailable_reason": "" if enabled else "needs STRIPE_SECRET_KEY and STRIPE_CONNECT_CLIENT_ID",
        "connected": bool(row and row["status"] == "connected"),
        "stripe_account_id": row["stripe_account_id"] if row else "",
        "charges_enabled": bool(row and row["charges_enabled"]),
        "payouts_enabled": bool(row and row["payouts_enabled"]),
    }


@owner_router.post("/connect/start")
async def connect_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not platform_configured():
        raise HTTPException(409, "Stripe Connect is disabled until STRIPE_SECRET_KEY and STRIPE_CONNECT_CLIENT_ID are configured")
    s = get_settings()
    redirect_uri = f"{s.public_base_url.rstrip('/')}/owner/payments/connect/callback"
    url = "https://connect.stripe.com/oauth/authorize?" + urlencode({
        "response_type": "code",
        "client_id": s.stripe_connect_client_id,
        "scope": "read_write",
        "redirect_uri": redirect_uri,
        "state": str(user["tenant_id"]),
    })
    return {"authorize_url": url}


@owner_router.post("/connect/disconnect")
async def connect_disconnect(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    await db.pool().execute(
        "UPDATE tenant_stripe_connect SET status='disconnected', charges_enabled=false, payouts_enabled=false, updated_at=now() "
        "WHERE tenant_id=$1",
        user["tenant_id"],
    )
    return {"connected": False}


class CheckoutBody(BaseModel):
    kind: Literal["deposit", "balance", "full"] = "full"


@invoice_router.post("/{invoice_id}/checkout")
async def create_invoice_checkout(
    invoice_id: str,
    body: CheckoutBody,
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "editor")
    if not platform_configured():
        raise HTTPException(409, "Stripe Connect is disabled until Jo configures Stripe Connect credentials")
    conn_row = await db.pool().fetchrow(
        "SELECT stripe_account_id, charges_enabled, status FROM tenant_stripe_connect WHERE tenant_id=$1",
        user["tenant_id"],
    )
    if not conn_row or conn_row["status"] != "connected" or not conn_row["charges_enabled"]:
        raise HTTPException(409, "Connect your Stripe account first before creating card checkout links")
    inv = await db.pool().fetchrow(
        "SELECT id, number, currency, total_cents, due_cents, deposit_cents, balance_cents, public_token, status "
        "FROM invoices WHERE id=$1 AND tenant_id=$2",
        invoice_id, user["tenant_id"],
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv["status"] in ("paid", "void"):
        raise HTTPException(409, f"Invoice is already {inv['status']}")
    if body.kind == "deposit":
        amount = int(inv["deposit_cents"] or inv["due_cents"] or inv["total_cents"])
    elif body.kind == "balance":
        amount = int(inv["balance_cents"] or inv["due_cents"] or inv["total_cents"])
    else:
        amount = int(inv["due_cents"] or inv["total_cents"])
    if amount <= 0:
        raise HTTPException(400, "No amount due for checkout")
    s = get_settings()
    base = s.public_base_url.rstrip("/")
    resp = await http(
        "POST",
        "https://api.stripe.com/v1/checkout/sessions",
        headers={
            "Authorization": f"Bearer {s.stripe_secret_key}",
            "Stripe-Account": conn_row["stripe_account_id"],
        },
        data={
            "mode": "payment",
            "line_items[0][price_data][currency]": (inv["currency"] or "NZD").lower(),
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": f"Invoice {inv['number']} ({body.kind})",
            "line_items[0][quantity]": "1",
            "success_url": f"{base}/invoice/{inv['public_token']}?paid=1",
            "cancel_url": f"{base}/invoice/{inv['public_token']}",
            "metadata[tenant_id]": str(user["tenant_id"]),
            "metadata[invoice_id]": str(inv["id"]),
            "metadata[payment_kind]": body.kind,
        },
    )
    if resp.status_code >= 300:
        raise HTTPException(502, "Stripe checkout session creation failed")
    session = resp.json()
    await db.pool().execute(
        "INSERT INTO invoice_payments(tenant_id, invoice_id, kind, method, amount_cents, currency, stripe_session_id, status) "
        "VALUES($1, $2, $3, 'stripe', $4, $5, $6, 'pending')",
        user["tenant_id"], inv["id"], body.kind, amount, inv["currency"] or "NZD", session["id"],
    )
    return {"checkout_url": session["url"], "session_id": session["id"], "amount_cents": amount}


@invoice_router.post("/{invoice_id}/balance-invoice", status_code=201)
async def create_balance_invoice(invoice_id: str, user: dict = Depends(owner_auth.current_user)):
    """Generate the follow-up balance invoice for an existing deposit invoice."""
    owner_auth.require_role(user, "editor")
    inv = await db.pool().fetchrow(
        "SELECT * FROM invoices WHERE id=$1 AND tenant_id=$2",
        invoice_id, user["tenant_id"],
    )
    if not inv:
        raise HTTPException(404, "Invoice not found")
    bal = int(inv["balance_cents"] or 0)
    if bal <= 0:
        raise HTTPException(409, "This invoice has no remaining balance")
    bal_number = f"{inv['number']}-BAL"
    existing = await db.pool().fetchval(
        "SELECT id FROM invoices WHERE tenant_id=$1 AND number=$2", user["tenant_id"], bal_number
    )
    if existing:
        raise HTTPException(409, "Balance invoice already exists")
    token = secrets.token_urlsafe(24)
    row = await db.pool().fetchrow(
        """INSERT INTO invoices(
               tenant_id, quotation_id, number, kind, status, subtotal_cents, tax_cents,
               total_cents, due_cents, deposit_cents, balance_cents, currency, lines, notes, public_token)
           VALUES($1, $2, $3, 'balance', 'issued', $4, 0, $4, $4, 0, 0, $5, $6::jsonb, $7, $8)
           RETURNING id, number, kind, status, due_cents, currency, public_token""",
        user["tenant_id"],
        inv["quotation_id"],
        bal_number,
        bal,
        inv["currency"] or "NZD",
        json.dumps([{"description": f"Balance remaining on {inv['number']}", "amount_cents": bal}]),
        f"Balance invoice following deposit invoice {inv['number']}",
        token,
    )
    return {**dict(row), "id": str(row["id"])}


def _verify_stripe_sig(payload: bytes, sig_header: str, secret: str) -> bool:
    parts = dict(item.split("=", 1) for item in (sig_header or "").split(",") if "=" in item)
    ts = parts.get("t")
    v1 = parts.get("v1")
    if not ts or not v1:
        return False
    signed = f"{ts}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@webhook_router.post("/webhooks/stripe-connect")
async def stripe_connect_webhook(request: Request):
    secret = (get_settings().stripe_connect_webhook_secret or "").strip()
    if not secret:
        raise HTTPException(503, "STRIPE_CONNECT_WEBHOOK_SECRET is not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature") or ""
    if not _verify_stripe_sig(payload, sig, secret):
        raise HTTPException(400, "Invalid Stripe signature")
    event = json.loads(payload.decode("utf-8"))
    if event.get("type") == "checkout.session.completed":
        obj = (event.get("data") or {}).get("object") or {}
        sess_id = obj.get("id") or ""
        meta = obj.get("metadata") or {}
        inv_id = meta.get("invoice_id")
        kind = meta.get("payment_kind") or "full"
        if sess_id:
            await db.pool().execute(
                "UPDATE invoice_payments SET status='paid', paid_at=now() WHERE stripe_session_id=$1",
                sess_id,
            )
        if inv_id:
            new_status = "deposit_paid" if kind == "deposit" else "paid"
            await db.pool().execute(
                "UPDATE invoices SET status=$2, due_cents=CASE WHEN $2='paid' THEN 0 ELSE due_cents END WHERE id=$1",
                inv_id, new_status,
            )
    return {"received": True}
