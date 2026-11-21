"""Concierge's own subscription lifecycle (N1).

`platform_billing` turns the first payment into an invoice and a business. This module handles what
happens after: renewals, declined cards (dunning), upgrades, cancellations and refunds, all driven by
signed Stripe webhooks, plus the Studio "Billing" tab's data and the Stripe Customer Portal link.

Rules:
  * Stripe is the source of truth; `tenants.billing_*` only mirrors it.
  * A declined card starts a grace period (BILLING_GRACE_DAYS). Only when it ends is the business
    paused, using the same pause switch the owner has (`tenant_pause`) with `paused_by='billing'`.
    Inbound enquiries are still captured while paused, so a lapsed subscriber loses no leads.
  * Payment, or a subscription returning to good standing, lifts a billing pause. A pause the owner
    set themselves is never lifted by billing.
  * Tenants with `billing_status='none'` (bank transfer, one-off payment) are never auto-suspended.
  * Every event is applied once (`stripe_events`); a handler that fails releases the event so Stripe's
    retry runs it again.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from . import db, owner_auth, owner_notifications, tenant_pause
from .config import get_settings

log = logging.getLogger("concierge.subscription")
router = APIRouter(tags=["billing"])

BILLING_PAUSER = "billing"
GOOD_STANDING = {"active", "trialing"}
# Stripe subscription statuses after which access should end (past_due gets the grace period instead).
SUSPEND_STATUSES = {"unpaid", "canceled", "incomplete_expired"}
HANDLED_EVENTS = {
    "invoice.paid", "invoice.payment_failed", "customer.subscription.updated",
    "customer.subscription.deleted", "charge.refunded",
}


def _ts(value) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def normalise_status(stripe_status: str) -> str:
    """Map Stripe's subscription status onto ours. Unknown values are kept, never guessed as active."""
    status = (stripe_status or "").lower()
    return status if status else "none"


def grace_deadline(now: datetime | None = None, days: int | None = None) -> datetime:
    days = get_settings().billing_grace_days if days is None else days
    return (now or datetime.now(timezone.utc)) + timedelta(days=max(0, int(days)))


def period_end(subscription: dict) -> datetime | None:
    """Stripe moved current_period_end onto the items in newer API versions; accept both."""
    value = subscription.get("current_period_end")
    if value is None:
        for item in ((subscription.get("items") or {}).get("data") or []):
            value = item.get("current_period_end")
            if value:
                break
    return _ts(value)


def plan_name(subscription: dict) -> str:
    for item in ((subscription.get("items") or {}).get("data") or []):
        price = item.get("price") or item.get("plan") or {}
        label = price.get("nickname") or (price.get("product") if isinstance(price.get("product"), str) else "")
        if label:
            return str(label)[:80]
    return (subscription.get("metadata") or {}).get("plan", "")[:80]


async def log_event(tenant_id, kind: str, detail: str = "") -> None:
    await db.pool().execute(
        "INSERT INTO billing_events(tenant_id,kind,detail) VALUES($1,$2,$3)",
        tenant_id, kind[:60], (detail or "")[:900])


async def find_tenant(*, customer_id: str = "", subscription_id: str = "", email: str = "") -> dict | None:
    """Match a Stripe object to a business: customer id, then subscription id, then a paid invoice's email."""
    pool = db.pool()
    if customer_id:
        row = await pool.fetchrow("SELECT * FROM tenants WHERE stripe_customer_id=$1", customer_id)
        if row:
            return dict(row)
    if subscription_id:
        row = await pool.fetchrow("SELECT * FROM tenants WHERE stripe_subscription_id=$1", subscription_id)
        if row:
            return dict(row)
    email = (email or "").strip().lower()
    if "@" in email:
        row = await pool.fetchrow(
            "SELECT t.* FROM platform_invoices i JOIN tenants t ON t.id=i.tenant_id "
            "WHERE i.customer_email=$1 ORDER BY i.created_at DESC LIMIT 1", email)
        if row:
            return dict(row)
    return None


async def link_checkout(tenant_id, session: dict) -> None:
    """Remember the Stripe customer/subscription from a completed checkout so later events can find us."""
    customer = session.get("customer") if isinstance(session.get("customer"), str) else ""
    subscription = session.get("subscription") if isinstance(session.get("subscription"), str) else ""
    if not (customer or subscription):
        return
    await db.pool().execute(
        "UPDATE tenants SET stripe_customer_id=COALESCE(NULLIF($2,''),stripe_customer_id), "
        "stripe_subscription_id=COALESCE(NULLIF($3,''),stripe_subscription_id), "
        "billing_status=CASE WHEN $3<>'' AND billing_status='none' THEN 'active' ELSE billing_status END "
        "WHERE id=$1", tenant_id, customer, subscription)


async def suspend(tenant: dict, reason: str) -> None:
    if tenant.get("paused_at"):
        return  # already off, by the owner or earlier by billing; do not overwrite who paused it
    await tenant_pause.set_paused(tenant["id"], True, BILLING_PAUSER)
    await log_event(tenant["id"], "suspended", reason)
    await _tell_owner(tenant, "Your Concierge is paused",
                      f"Concierge has paused for {tenant['name']}: {reason}\n\n"
                      "Enquiries are still captured and nothing is lost. Update your payment details under "
                      "Billing in Studio and it resumes straight away.", f"billing-suspended:{tenant['id']}:{reason}")


async def restore(tenant: dict) -> None:
    """Lift a pause that billing caused. A pause the owner chose stays."""
    row = await db.pool().fetchrow("SELECT paused_at, paused_by FROM tenants WHERE id=$1", tenant["id"])
    if row and row["paused_at"] is not None and row["paused_by"] == BILLING_PAUSER:
        await tenant_pause.set_paused(tenant["id"], False, "")
        await log_event(tenant["id"], "resumed", "Payment received")


async def _tell_owner(tenant: dict, subject: str, body: str, dedupe: str) -> None:
    try:
        await owner_notifications.queue(tenant, subject, body, dedupe)
    except Exception:  # noqa: BLE001 - a failed notice must not make Stripe retry a finished state change
        log.exception("could not queue billing notice for %s", tenant.get("slug"))


async def _tell_operator(subject: str, body: str, dedupe: str) -> None:
    operator = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug='trendi-support'")
    if operator:
        await _tell_owner(dict(operator), subject, body, dedupe)


# ---- event handlers ----------------------------------------------------------------------------

async def on_invoice_paid(invoice: dict, event_id: str = "") -> None:
    tenant = await find_tenant(customer_id=invoice.get("customer") or "",
                               subscription_id=invoice.get("subscription") or "",
                               email=invoice.get("customer_email") or "")
    if not tenant:
        return  # the first payment is matched by checkout.session.completed; nothing to renew yet
    await db.pool().execute(
        "UPDATE tenants SET billing_status='active', billing_grace_until=NULL, "
        "stripe_customer_id=COALESCE(stripe_customer_id,NULLIF($2,'')), "
        "stripe_subscription_id=COALESCE(stripe_subscription_id,NULLIF($3,'')) WHERE id=$1",
        tenant["id"], invoice.get("customer") or "", invoice.get("subscription") or "")
    await restore(tenant)
    # The initial subscription invoice already became a platform invoice via checkout; only renewals
    # and later cycles get a new tax invoice here.
    if invoice.get("billing_reason") == "subscription_create":
        return
    amount = invoice.get("amount_paid")
    if not isinstance(amount, int) or amount <= 0 or not invoice.get("id"):
        return
    from . import platform_billing  # local: platform_billing imports this module
    currency = (invoice.get("currency") or "nzd").upper()[:3]
    gst_rate = platform_billing.GST_RATE if currency == "NZD" else 0.0
    gst, _net = platform_billing.gst_split(amount, rate=gst_rate)
    email = (invoice.get("customer_email") or tenant.get("notify_email") or "").strip().lower()
    number = await platform_billing.next_number()
    import secrets
    row = await db.pool().fetchrow(
        "INSERT INTO platform_invoices(number,customer_email,customer_name,business_name,plan,amount_cents,"
        "gst_cents,currency,status,source,stripe_event_id,stripe_invoice_id,tenant_id,public_token,"
        "issued_on,paid_at,description) VALUES($1,$2,$3,$4,'Concierge',$5,$6,$7,'paid','stripe-renewal',$8,$9,$10,"
        "$11,current_date,now(),$12) ON CONFLICT (stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL "
        "DO NOTHING RETURNING *",
        number, email, (invoice.get("customer_name") or "")[:120], tenant["name"][:160], amount, gst,
        currency, event_id[:120], invoice["id"], tenant["id"],
        secrets.token_urlsafe(24), "Concierge subscription renewal")
    if row and "@" in email:
        await platform_billing.email_invoice(dict(row))
        await db.pool().execute("UPDATE platform_invoices SET emailed_at=now() WHERE id=$1", row["id"])


async def on_payment_failed(invoice: dict, event_id: str = "") -> None:
    tenant = await find_tenant(customer_id=invoice.get("customer") or "",
                               subscription_id=invoice.get("subscription") or "",
                               email=invoice.get("customer_email") or "")
    if not tenant:
        return
    deadline = grace_deadline()
    await db.pool().execute(
        "UPDATE tenants SET billing_status='past_due', "
        "billing_grace_until=COALESCE(billing_grace_until,$2) WHERE id=$1", tenant["id"], deadline)
    await log_event(tenant["id"], "payment_failed", f"invoice {invoice.get('id', '')}")
    until = (await db.pool().fetchval(
        "SELECT billing_grace_until FROM tenants WHERE id=$1", tenant["id"])) or deadline
    await _tell_owner(
        tenant, "Your Concierge payment did not go through",
        f"We could not take your latest Concierge payment for {tenant['name']}.\n\n"
        f"Concierge keeps working until {until:%d %b %Y}. Please update your card under Billing in Studio "
        "before then; Stripe will retry automatically once you do.",
        f"billing-failed:{invoice.get('id', event_id)}:{invoice.get('attempt_count', 0)}")


async def on_subscription_updated(subscription: dict, event_id: str = "") -> None:
    tenant = await find_tenant(customer_id=subscription.get("customer") or "",
                               subscription_id=subscription.get("id") or "")
    if not tenant:
        return
    status = normalise_status(subscription.get("status", ""))
    await db.pool().execute(
        "UPDATE tenants SET billing_status=$2, billing_period_end=COALESCE($3,billing_period_end), "
        "billing_cancel_at_period_end=$4, stripe_subscription_id=COALESCE(NULLIF($5,''),stripe_subscription_id), "
        "stripe_customer_id=COALESCE(stripe_customer_id,NULLIF($6,'')), "
        "billing_grace_until=CASE WHEN $2 IN ('active','trialing') THEN NULL ELSE billing_grace_until END "
        "WHERE id=$1",
        tenant["id"], status, period_end(subscription), bool(subscription.get("cancel_at_period_end")),
        subscription.get("id") or "", subscription.get("customer") or "")
    plan = plan_name(subscription)
    await log_event(tenant["id"], "subscription_updated",
                    f"status={status} plan={plan} cancel_at_period_end={bool(subscription.get('cancel_at_period_end'))}")
    if status in GOOD_STANDING:
        await restore(tenant)
    elif status in SUSPEND_STATUSES:
        await suspend(tenant, f"your subscription is {status.replace('_', ' ')}")
    elif status == "past_due" and not tenant.get("billing_grace_until"):
        await db.pool().execute(
            "UPDATE tenants SET billing_grace_until=COALESCE(billing_grace_until,$2) WHERE id=$1",
            tenant["id"], grace_deadline())


async def on_subscription_deleted(subscription: dict, event_id: str = "") -> None:
    tenant = await find_tenant(customer_id=subscription.get("customer") or "",
                               subscription_id=subscription.get("id") or "")
    if not tenant:
        return
    await db.pool().execute(
        "UPDATE tenants SET billing_status='canceled', billing_grace_until=NULL, "
        "billing_cancel_at_period_end=false WHERE id=$1", tenant["id"])
    await log_event(tenant["id"], "subscription_deleted", subscription.get("id") or "")
    await suspend(tenant, "your subscription has ended")
    await _tell_operator("Subscription cancelled — " + tenant["name"],
                         f"{tenant['name']} ({tenant['slug']}) cancelled; the business is paused.",
                         f"billing-cancelled-op:{tenant['id']}:{subscription.get('id', '')}")


async def on_charge_refunded(charge: dict, event_id: str = "") -> None:
    tenant = await find_tenant(customer_id=charge.get("customer") or "",
                               email=(charge.get("billing_details") or {}).get("email") or "")
    amount = charge.get("amount") or 0
    refunded = charge.get("amount_refunded") or 0
    tenant_id = tenant["id"] if tenant else None
    await log_event(tenant_id, "refund", f"charge {charge.get('id', '')}: {refunded}/{amount} {charge.get('currency', '')}")
    if tenant and amount and refunded >= amount:
        await db.pool().execute(
            "UPDATE platform_invoices SET status='refunded' WHERE id=("
            "SELECT id FROM platform_invoices WHERE tenant_id=$1 AND status='paid' AND amount_cents=$2 "
            "ORDER BY paid_at DESC NULLS LAST LIMIT 1)", tenant["id"], int(amount))
    await _tell_operator(
        "Stripe refund" + (f" — {tenant['name']}" if tenant else ""),
        f"Charge {charge.get('id', '')} refunded {refunded / 100:,.2f} of {amount / 100:,.2f} "
        f"{(charge.get('currency') or '').upper()}. Decide whether the business keeps access.",
        f"billing-refund:{charge.get('id', event_id)}:{refunded}")


HANDLERS = {
    "invoice.paid": on_invoice_paid,
    "invoice.payment_failed": on_payment_failed,
    "customer.subscription.updated": on_subscription_updated,
    "customer.subscription.deleted": on_subscription_deleted,
    "charge.refunded": on_charge_refunded,
}


async def handle_event(event: dict) -> bool:
    """Apply one verified Stripe event exactly once. Returns False for events we do not act on."""
    kind = event.get("type", "")
    handler = HANDLERS.get(kind)
    event_id = str(event.get("id") or "")
    if handler is None or not event_id:
        return False
    fresh = await db.pool().fetchval(
        "INSERT INTO stripe_events(event_id,kind) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING true",
        event_id, kind)
    if not fresh:
        return False  # Stripe retried an event we already applied
    try:
        await handler((event.get("data") or {}).get("object") or {}, event_id)
    except Exception:
        # Release the event so Stripe's retry gets another go instead of being swallowed as a duplicate.
        await db.pool().execute("DELETE FROM stripe_events WHERE event_id=$1", event_id)
        raise
    return True


# ---- grace-period sweep ------------------------------------------------------------------------

async def sweep() -> int:
    """Pause every business whose grace period has run out. Returns how many were paused."""
    rows = await db.pool().fetch(
        "SELECT * FROM tenants WHERE billing_status='past_due' AND billing_grace_until IS NOT NULL "
        "AND billing_grace_until < now() AND paused_at IS NULL")
    for row in rows:
        await suspend(dict(row), "your payment is overdue")
    return len(rows)


async def run_forever(stop: asyncio.Event, every: int = 3600) -> None:
    while not stop.is_set():
        try:
            await sweep()
        except Exception:  # noqa: BLE001 - retry next hour
            log.exception("billing grace sweep failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=every)
        except asyncio.TimeoutError:
            pass


# ---- Studio: Billing tab -----------------------------------------------------------------------

def _owner_only(user: dict) -> None:
    if (user.get("role") or "") != "owner":
        raise HTTPException(403, "Owner only")


@router.get("/owner/billing/status")
async def billing_status(user: dict = Depends(owner_auth.current_user)):
    _owner_only(user)
    row = await db.pool().fetchrow(
        "SELECT billing_status, billing_grace_until, billing_period_end, billing_cancel_at_period_end, "
        "stripe_customer_id, paused_at, paused_by FROM tenants WHERE id=$1", user["tenant_id"])
    if not row:
        raise HTTPException(404, "Business not found")
    settings = get_settings()
    return {
        "status": row["billing_status"],
        "grace_until": row["billing_grace_until"].isoformat() if row["billing_grace_until"] else None,
        "renews_on": row["billing_period_end"].isoformat() if row["billing_period_end"] else None,
        "cancels_at_period_end": row["billing_cancel_at_period_end"],
        "paused_for_billing": row["paused_at"] is not None and row["paused_by"] == BILLING_PAUSER,
        "portal_available": bool(settings.stripe_secret_key and row["stripe_customer_id"]),
    }


@router.post("/owner/billing/portal")
async def billing_portal(user: dict = Depends(owner_auth.current_user)):
    """A one-time Stripe Customer Portal link: update card, see invoices, cancel or change plan."""
    _owner_only(user)
    settings = get_settings()
    customer = await db.pool().fetchval(
        "SELECT stripe_customer_id FROM tenants WHERE id=$1", user["tenant_id"])
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Self-serve billing is not switched on yet. Email us and we will sort it.")
    if not customer:
        raise HTTPException(409, "No card subscription is linked to this business.")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://api.stripe.com/v1/billing_portal/sessions",
                data={"customer": customer, "return_url": settings.stripe_portal_return_url},
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"})
        response.raise_for_status()
        url = response.json().get("url", "")
    except (httpx.HTTPError, ValueError):
        log.exception("stripe portal session failed")
        raise HTTPException(502, "Could not open the billing portal. Try again shortly.") from None
    if not url.startswith("https://"):
        raise HTTPException(502, "Could not open the billing portal. Try again shortly.")
    return {"url": url}
