"""Billing for Concierge itself: someone buys, we are paid, and an invoice exists.

Conrad's invoices are for his customers. This is the other direction — Trendi selling the platform.
The website's buttons are Stripe Payment Links (`buy.stripe.com/...`), so the trustworthy signal that
money arrived is a signed Stripe webhook, not a URL parameter and not an operator's memory.

What happens on a verified payment, in one pass:

  1. the Stripe signature is checked against the raw body (constant-time, with a replay window);
  2. the event must say the session is actually paid — `checkout.session.completed` on an unpaid
     session is not money;
  3. a platform invoice is issued, numbered, marked paid, with GST broken out;
  4. a business is provisioned and its owner gets a sign-in link;
  5. the customer is emailed the invoice immediately, through the outbox so it is recorded and
     retried;
  6. the operator is told.

Idempotency is the session id: Stripe retries webhooks, and a retry must never issue a second
invoice or a second business.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import time
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, owner_auth, owner_invites, outbox, owner_notifications, subscription, tenants
from .config import get_settings
from .security import require_admin

router = APIRouter(tags=["billing"])
public_router = APIRouter(prefix="/receipt", tags=["billing"])

TOLERANCE_SECONDS = 300
GST_RATE = 0.15


def verify_signature(payload: bytes, header: str, secret: str, *, now: float | None = None,
                     tolerance: int = TOLERANCE_SECONDS) -> bool:
    """Standard Stripe scheme: `t=<unix>,v1=<hmac of "t.body">`.

    The body must be the raw bytes exactly as received — re-serialising JSON changes the signature.
    """
    if not header or not secret:
        return False
    pairs = [part.strip().split("=", 1) for part in header.split(",") if "=" in part]
    timestamp_raw = next((v for k, v in pairs if k == "t"), "")
    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        return False
    v1_sigs = [v for k, v in pairs if k == "v1" and v]
    if not v1_sigs:
        return False
    clock = time.time() if now is None else now
    if abs(clock - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in v1_sigs)


def gst_rate_for(currency: str, customer_country: str = "") -> float:
    """NZ customers pay 15% GST (included in the stated price); everyone else is GST-exempt (0%).

    When no country is provided (e.g. a manual NZD bank transfer), NZD implies a New Zealand supply.
    """
    country = (customer_country or "").strip().upper()
    if country:
        return GST_RATE if country == "NZ" else 0.0
    return GST_RATE if (currency or "").strip().upper() == "NZD" else 0.0


def gst_split(amount_cents: int, rate: float = GST_RATE) -> tuple[int, int]:
    """GST-inclusive totals: the GST component, and the ex-GST subtotal."""
    total = max(0, int(amount_cents))
    if rate <= 0:
        return 0, total
    gst = round(total * rate / (1 + rate))
    return gst, total - gst


async def next_number() -> str:
    value = await db.pool().fetchval("SELECT nextval('platform_invoice_seq')")
    return f"TRB-{int(value):04d}"


async def issue(*, email: str, name: str, business: str, plan: str, amount_cents: int,
                currency: str = "NZD", customer_country: str = "", source: str = "stripe",
                stripe_session_id: str | None = None, stripe_event_id: str = "",
                description: str = "", tenant_id=None) -> dict:
    """Idempotent on the Stripe session: a retried webhook returns the invoice already issued."""
    email = email.strip().lower()
    if stripe_session_id:
        existing = await db.pool().fetchrow(
            "SELECT * FROM platform_invoices WHERE stripe_session_id=$1", stripe_session_id)
        if existing:
            return dict(existing)
    norm_currency = (currency or "NZD").upper()[:3]
    gst_rate = gst_rate_for(norm_currency, customer_country)
    gst_cents, net_cents = gst_split(amount_cents, rate=gst_rate)
    number = await next_number()
    token = secrets.token_urlsafe(24)
    row = await db.pool().fetchrow(
        "INSERT INTO platform_invoices(number,customer_email,customer_name,business_name,plan,"
        "amount_cents,gst_cents,currency,status,source,stripe_session_id,stripe_event_id,tenant_id,"
        "public_token,issued_on,paid_at,description) "
        "VALUES($1,$2,$3,$4,$5,$6,$7,$8,'paid',$9,$10,$11,$12,$13,current_date,now(),$14) "
        "ON CONFLICT (stripe_session_id) DO NOTHING RETURNING *",
        number, email, name[:120], business[:160], plan[:80], int(amount_cents), gst_cents,
        norm_currency, source, stripe_session_id, stripe_event_id[:120],
        tenant_id, token, description[:500] or f"Concierge — {plan}"[:500])
    if row is None:  # lost a race with a retry; the other transaction's invoice stands
        row = await db.pool().fetchrow(
            "SELECT * FROM platform_invoices WHERE stripe_session_id=$1", stripe_session_id)
    return dict(row)


def invoice_html(invoice: dict) -> str:
    """A paid tax invoice. There is no balance to chase and no accept button."""
    gst = invoice["gst_cents"] / 100
    total = invoice["amount_cents"] / 100
    net = total - gst
    paid = html.escape(invoice["paid_at"].strftime("%d %b %Y") if invoice.get("paid_at") else "")
    issued_raw = invoice.get("issued_on")
    issued = html.escape(f"{issued_raw:%d %b %Y}" if hasattr(issued_raw, "strftime") else str(issued_raw or ""))
    number = html.escape(str(invoice.get("number") or ""))
    email = html.escape(str(invoice.get("customer_email") or ""))
    name = html.escape(str(invoice.get("customer_name") or invoice.get("customer_email") or ""))
    business = html.escape(str(invoice.get("business_name") or ""))
    description = html.escape(str(invoice.get("description") or ""))
    currency = html.escape(str(invoice.get("currency") or ""))
    gst_label = "GST (15%)" if gst > 0 else "GST (0% — zero-rated export)"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noai, noimageai"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Invoice {number} — TRENDI LIMITED</title>
<style>body{{font-family:system-ui,-apple-system,sans-serif;margin:0;color:#15191f;background:#f6f8fa}}
.page{{max-width:760px;margin:32px auto;background:#fff;padding:40px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.08)}}
header{{display:flex;justify-content:space-between;border-bottom:6px solid #c8f560;padding-bottom:18px}}
h1{{margin:6px 0;font-size:26px}} .muted{{color:#5a6673;font-size:14px}}
table{{width:100%;border-collapse:collapse;margin-top:24px}} td,th{{padding:10px 8px;border-bottom:1px solid #e3e7ec;text-align:left}}
.num{{text-align:right}} .paid{{display:inline-block;background:#e7f8d0;color:#2b4a00;padding:6px 12px;border-radius:999px;font-weight:700;font-size:13px}}
</style></head><body><div class="page">
<header><div><div class="muted">TRENDI LIMITED (NZBN 9429051967215 · GST 142-296-901)</div><h1>Tax invoice</h1>
<div class="muted">{number}</div></div>
<div class="muted">{issued}<br><span class="paid">PAID {paid}</span></div></header>
<p><strong>{name}</strong>{('<br>' + business) if business else ''}<br>{email}</p>
<table><thead><tr><th>Description</th><th class="num">Amount</th></tr></thead><tbody>
<tr><td>{description}</td><td class="num">{net:,.2f} {currency}</td></tr>
<tr><td>{gst_label}</td><td class="num">{gst:,.2f} {currency}</td></tr>
<tr><td><strong>Total paid</strong></td><td class="num"><strong>{total:,.2f} {currency}</strong></td></tr>
</tbody></table>
<p class="muted" style="margin-top:26px">Paid in full. This is your tax invoice — keep it for your records.</p>
</div></body></html>"""


async def email_invoice(invoice: dict) -> None:
    """Send the invoice the moment payment is verified. Recorded in the outbox, so it retries.

    The outbox row needs a business. Before provisioning there is none, so the platform's own
    business owns the row — the sale is Trendi's, and the email must not wait on provisioning.
    """
    owner_tenant = invoice.get("tenant_id") or await db.pool().fetchval(
        "SELECT id FROM tenants WHERE slug='trendi-support' LIMIT 1")
    if not owner_tenant:
        return
    base = (get_settings().public_base_url or "https://concierge.trendibizz.com").rstrip("/")
    link = f"{base}/receipt/{invoice['public_token']}"
    total = invoice["amount_cents"] / 100
    body = (f"Thanks — your payment of {total:,.2f} {invoice['currency']} has been received and verified.\n\n"
            f"Invoice {invoice['number']} is attached to this payment and is also here:\n{link}\n\n"
            f"Your Concierge portal is being set up; a separate email will give you your sign-in link.\n")
    await outbox.enqueue(
        owner_tenant, "customer_invoice", "email", invoice["customer_email"], body,
        subject=f"Invoice {invoice['number']} — Trendi Concierge",
        dedupe_key=f"platform-invoice:{invoice['number']}:{invoice['customer_email']}")


async def provision(invoice: dict) -> dict:
    """Give the buyer a way in: a business and an owner sign-in link."""
    slug = "client-" + invoice["number"].lower().replace("trb-", "")
    business = invoice.get("business_name") or invoice.get("customer_name") or invoice["customer_email"]
    # tenants.create() is the one place that knows the required columns (public_key, report_token).
    # Inserting a tenant by hand here is how a verified purchase ended up with no business at all.
    await tenants.create(business[:120], None, slug=slug)
    tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug=$1", slug)
    if not tenant:
        raise RuntimeError("Business was not created")
    await db.pool().execute(
        "UPDATE tenants SET notify_email=$2 WHERE id=$1", tenant["id"], invoice["customer_email"])
    await db.pool().execute(
        "INSERT INTO tenant_users(tenant_id,email,role,password_hash,active) "
        "VALUES($1,$2,'owner','',true) "
        "ON CONFLICT (tenant_id,email) DO NOTHING", tenant["id"], invoice["customer_email"])
    await owner_invites.send(slug, invoice["customer_email"])
    await db.pool().execute(
        "UPDATE platform_invoices SET tenant_id=$2 WHERE id=$1", invoice["id"], tenant["id"])
    invoice["tenant_id"] = tenant["id"]
    return dict(tenant)


async def handle_checkout(session: dict, event_id: str = "") -> dict | None:
    """A verified Stripe checkout. Nothing is issued unless the session is actually paid."""
    if (session.get("payment_status") or "").lower() not in ("paid", "no_payment_required"):
        return None
    amount = session.get("amount_total")
    if not isinstance(amount, int) or amount <= 0:
        return None
    details = session.get("customer_details") or {}
    email = (details.get("email") or session.get("customer_email") or "").strip().lower()
    if "@" not in email:
        return None
    customer_country = ((details.get("address") or {}).get("country") or "").strip().upper()
    invoice = await issue(
        email=email,
        name=(details.get("name") or "").strip(),
        business=(session.get("metadata") or {}).get("business", ""),
        plan=(session.get("metadata") or {}).get("plan", "Concierge"),
        amount_cents=amount,
        currency=session.get("currency") or "NZD",
        customer_country=customer_country,
        source="stripe",
        stripe_session_id=session.get("id"),
        stripe_event_id=event_id,
        description=(session.get("metadata") or {}).get("plan", "Concierge subscription"),
    )
    # The money is already taken, so the invoice must go out regardless of anything that follows.
    # Provisioning is attempted first only because a working portal link is the better email; its
    # failure is recorded for a person and never stops the invoice.
    provision_error = None
    if not invoice.get("tenant_id"):
        try:
            await provision(invoice)
        except Exception as error:  # noqa: BLE001 - the sale stands; a person must fix the business
            provision_error = error
            await subscription.log_event(
                None, "provision_failed", f"{invoice['number']} {invoice['customer_email']}: {error}")
    if invoice.get("tenant_id"):
        await subscription.link_checkout(invoice["tenant_id"], session)
    if not invoice.get("emailed_at"):
        await email_invoice(dict(invoice))
        await db.pool().execute(
            "UPDATE platform_invoices SET emailed_at=now() WHERE id=$1", invoice["id"])
    operator = await db.pool().fetchrow(
        "SELECT t.* FROM tenants t WHERE t.slug='trendi-support'")
    if operator:
        prov_line = (
            f"PROVISIONING FAILED — manual follow-up needed: {provision_error}"
            if provision_error
            else f"Business provisioned: {invoice.get('business_name') or invoice['customer_email']}."
        )
        await owner_notifications.queue(
            dict(operator), "Payment received — " + invoice["number"],
            f"{invoice['customer_email']} paid {invoice['amount_cents'] / 100:,.2f} "
            f"{invoice['currency']} ({invoice['plan']}).\nInvoice issued and emailed.\n"
            f"{prov_line}",
            f"platform-sale:{invoice['id']}")
    return invoice


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="")):
    """Stripe calls this. Signature first, raw body, then the event."""
    settings = get_settings()
    raw = await request.body()
    secret = getattr(settings, "stripe_webhook_secret", "") or ""
    if not secret or not verify_signature(raw, stripe_signature, secret):
        raise HTTPException(400, "Invalid signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid payload") from None
    kind = event.get("type", "")
    data = (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed":
        await handle_checkout(data, event.get("id", ""))
    else:
        await subscription.handle_event(event)
    return {"received": True}


class ManualCharge(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=120)
    business: str = Field(default="", max_length=160)
    plan: str = Field(default="Concierge", max_length=80)
    amount_cents: int = Field(gt=0)
    currency: str = Field(default="NZD", min_length=3, max_length=3)
    customer_country: str = Field(default="", max_length=2)
    reference: str = Field(default="", max_length=120)


@router.post("/admin/billing/charge", dependencies=[Depends(require_admin)])
async def manual_charge(body: ManualCharge):
    """A bank transfer, verified by a person. Same outcome: invoice, provisioning, email."""
    invoice = await issue(
        email=body.email, name=body.name, business=body.business, plan=body.plan,
        amount_cents=body.amount_cents, currency=body.currency.upper(),
        customer_country=body.customer_country,
        source="manual:" + (body.reference or "bank"), description=body.plan)
    if not invoice.get("emailed_at"):
        await email_invoice(invoice)
        await db.pool().execute(
            "UPDATE platform_invoices SET emailed_at=now() WHERE id=$1", invoice["id"])
    if not invoice.get("tenant_id"):
        await provision(invoice)
    return invoice


@public_router.get("/{token}", response_class=HTMLResponse)
async def receipt(token: str):
    row = await db.pool().fetchrow("SELECT * FROM platform_invoices WHERE public_token=$1", token)
    if not row:
        raise HTTPException(404, "Invoice not found")
    return HTMLResponse(invoice_html(dict(row)))


@router.get("/owner/billing/invoices")
async def platform_list(user: dict = Depends(owner_auth.current_user)):
    if (user.get("role") or "") != "owner":
        raise HTTPException(403, "Owner only")
    rows = await db.pool().fetch(
        "SELECT id,number,customer_email,customer_name,business_name,plan,amount_cents,gst_cents,"
        "currency,status,source,issued_on,paid_at,public_token FROM platform_invoices "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200",
        user["tenant_id"],
    )
    return [dict(row) for row in rows]
