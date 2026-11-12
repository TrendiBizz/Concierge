"""Getting paid on an accepted quotation — without adding a payment processor.

Competitor-gap item E. GoHighLevel includes payments/invoicing on every plan, and the operator's
constraint on this build is that nothing may depend on a paid service (and nothing on Microsoft).
So this is deliberately processor-free:

  * the business records its own payment instructions (bank details, or any link it already uses),
  * an accepted quotation shows those instructions to the customer with one button,
  * the customer says "I have paid" (optionally with a reference),
  * the owner confirms it, which records who decided what and when.

That is the whole money trail an owner of a quote-and-invoice trade needs, it costs nothing, and it
gives item F real numbers. Stripe (or any provider) can be added later behind the same state
machine — the schema records declarations and confirmations, not card data, so nothing here has to
be thrown away.

Rules that matter:
  * only an accepted quotation can be declared paid on, and the public endpoint is idempotent;
  * a declaration is never treated as a payment: only an owner confirmation sets `paid`;
  * every transition is appended to `quote_payments`, so F can report on money rather than guesses.
"""

import logging
from datetime import datetime, timezone

from . import db, owner_notifications

log = logging.getLogger("concierge.quote_payments")

PAYMENT_STATES = ("unpaid", "declared", "paid", "waived")
CONFIRMABLE = ("unpaid", "declared")


def state_of(quote: dict) -> str:
    """The payment state, defensively: an unknown stored value is treated as unpaid."""
    value = (quote.get("payment_status") or "unpaid").strip().lower()
    return value if value in PAYMENT_STATES else "unpaid"


def can_declare(quote: dict) -> bool:
    """A customer may say they have paid only on an accepted, still-unpaid quotation."""
    return (quote.get("status") == "accepted") and state_of(quote) == "unpaid"


def can_confirm(quote: dict) -> bool:
    """The owner may confirm any accepted quotation that is not already paid."""
    return (quote.get("status") == "accepted") and state_of(quote) in CONFIRMABLE


def instructions_for(tenant: dict | None) -> dict:
    """What the customer is told to do. Empty instructions mean card/link payment is not offered."""
    tenant = tenant or {}
    text = (tenant.get("payment_instructions") or "").strip()
    url = (tenant.get("payment_url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        url = ""  # never render a javascript: or relative URL as a payment destination
    return {"instructions": text, "url": url, "available": bool(text or url)}


def customer_message(quote: dict, tenant: dict | None) -> str:
    """The sentence the public page shows, in the customer's terms."""
    state = state_of(quote)
    if quote.get("status") != "accepted":
        return "This quotation is not accepted yet, so there is nothing to pay."
    if state == "paid":
        return "Payment received. Thank you."
    if state == "waived":
        return "No payment is required on this quotation."
    if state == "declared":
        return "You told us you have paid. The business will confirm it — nothing else is needed."
    return ""


async def _event(tenant_id, quotation_id, kind: str, *, amount_cents: int = 0,
                 reference: str = "", by: str = "") -> None:
    await db.pool().execute(
        """INSERT INTO quote_payments(tenant_id, quotation_id, kind, amount_cents, reference, by_kind)
           VALUES($1,$2,$3,$4,$5,$6)""",
        tenant_id, quotation_id, kind, amount_cents, reference[:200], by[:120],
    )


async def declare(quote: dict, *, reference: str = "") -> dict:
    """The customer says they have paid. Idempotent; never marks anything paid."""
    state = state_of(quote)
    if not can_declare(quote):
        return {"ok": False, "reason": f"A quotation in state '{quote.get('status')}/{state}' "
                                       "cannot be declared paid.", "payment_status": state}
    row = await db.pool().fetchrow(
        """UPDATE quotations SET payment_status='declared', payment_reference=$3,
                                  payment_declared_at=now(), updated_at=now()
           WHERE id=$1 AND tenant_id=$2 AND payment_status='unpaid'
           RETURNING id, payment_status""",
        quote["id"], quote["tenant_id"], reference[:200],
    )
    if not row:
        return {"ok": False, "reason": "That quotation has already been updated.",
                "payment_status": state_of(quote)}
    await _event(quote["tenant_id"], quote["id"], "declared",
                 amount_cents=int(quote.get("total_cents") or 0), reference=reference,
                 by="customer")
    return {"ok": True, "payment_status": "declared"}


async def confirm(quote: dict, *, by: str = "owner", waive: bool = False) -> dict:
    """The owner confirms the money arrived (or waives it). The only path to `paid`."""
    if not can_confirm(quote):
        return {"ok": False, "reason": f"A quotation in state '{quote.get('status')}/"
                                       f"{state_of(quote)}' cannot be confirmed.",
                "payment_status": state_of(quote)}
    target = "waived" if waive else "paid"
    row = await db.pool().fetchrow(
        """UPDATE quotations SET payment_status=$3,
                                  payment_confirmed_at=CASE WHEN $3='paid' THEN now()
                                                            ELSE payment_confirmed_at END,
                                  updated_at=now()
           WHERE id=$1 AND tenant_id=$2 AND payment_status IN ('unpaid','declared')
           RETURNING id, payment_status""",
        quote["id"], quote["tenant_id"], target,
    )
    if not row:
        return {"ok": False, "reason": "That quotation has already been updated.",
                "payment_status": state_of(quote)}
    await _event(quote["tenant_id"], quote["id"], target,
                 amount_cents=int(quote.get("total_cents") or 0),
                 reference=quote.get("payment_reference") or "", by=by)
    return {"ok": True, "payment_status": target}


async def notify_declared(quote: dict, reference: str = "") -> None:
    """Tell the owner, immediately, that a customer claims to have paid."""
    row = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", quote["tenant_id"])
    if not row:
        return
    tenant = dict(row)
    amount = f"{(int(quote.get('total_cents') or 0)) / 100:,.2f} {quote.get('currency') or ''}".strip()
    await owner_notifications.queue(
        tenant,
        f"Payment claimed: {quote.get('title') or 'quotation'}",
        f"The customer says they have paid {amount}.\n"
        f"Quotation: {quote.get('title') or ''}\n"
        f"Reference: {reference or '-'}\n\n"
        "Confirm it in Studio -> Quotes once the money is in your account.",
        f"payment-declared:{quote['id']}",
    )


async def summary(tenant_id) -> dict:
    """Money actually confirmed, and money promised — the two numbers an owner acts on."""
    row = await db.pool().fetchrow(
        """SELECT
             COALESCE(SUM(total_cents) FILTER (WHERE payment_status='paid'), 0) AS paid_cents,
             COALESCE(SUM(total_cents) FILTER (WHERE payment_status='declared'), 0) AS declared_cents,
             COALESCE(SUM(total_cents) FILTER (WHERE status='accepted'
                                               AND payment_status IN ('unpaid','declared')), 0)
               AS outstanding_cents,
             count(*) FILTER (WHERE payment_status='declared') AS declared_count,
             count(*) FILTER (WHERE payment_status='paid') AS paid_count
           FROM quotations WHERE tenant_id=$1""",
        tenant_id,
    )
    data = dict(row) if row else {}
    return {key: int(value or 0) for key, value in data.items()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
