# Selling Concierge: paid → invoiced → provisioned

There was no path from a Stripe payment on the website to anything in the product. A customer could
pay and receive nothing but a Stripe receipt, and no invoice existed for the sale.

## What exists now

`api/app/platform_billing.py` + `platform_invoices`:

1. **`POST /webhooks/stripe`** — signature checked against the raw body (`t=<unix>,v1=<hmac>`),
   constant-time compare, five-minute replay window, fails closed if no secret is configured.
2. **Only money counts** — `checkout.session.completed` on a session whose `payment_status` is not
   `paid` (or `no_payment_required`) is ignored; a zero or missing amount is ignored.
3. **Invoice issued** — numbered `TRB-0001`…, GST broken out of the total paid (GST-inclusive, so
   GST = total × 15/115), marked paid with the payment date.
4. **Business provisioned** — a tenant via `tenants.create()`, the buyer as owner, a sign-in link.
5. **Invoice emailed immediately** — through the outbox, so it is recorded and retried; the email
   carries the public link `https://concierge.trendibizz.com/receipt/{token}`.
6. **Operator told** — "Payment received — TRB-000n" with the amount, plan and business.

**Idempotency** keys on the Stripe session id: a retried webhook returns the invoice that already
exists and re-emails nothing (`emailed_at`).

**Manual payments** (bank transfer, verified by a person): `POST /admin/billing/charge` with
`X-Admin-Token` takes the same path — invoice, provisioning, email.

**Receipt page** `/receipt/{token}` is a paid tax invoice: Trendi Bizz Limited, invoice number,
issue date, PAID badge, description, net, GST (15%), total, buyer name/business.

## Live proof (signed webhook against production, throwaway buyer since deleted)

| Step | Result |
|---|---|
| Forged signature | **400** |
| Signed `checkout.session.completed`, $1,150.00 NZD | **200** → `TRB-0003` paid, GST 150.00, provisioned, emailed |
| Same event repeated (Stripe retry) | **200**, still **one** invoice for that session |
| Invoice email | `customer_invoice` → **sent, attempts 1** |
| Receipt page | **200** with Tax invoice, PAID, GST line, 1,150.00 / 150.00 |
| Second purchase, $2,300.00 | **200** → `TRB-0004`, GST 300.00 |

## Faults found and fixed while building it

1. **Provisioning crashed** — a hand-rolled `INSERT INTO tenants` missed `public_key` (NOT NULL), so
   a paid customer got no business. Now uses `tenants.create()`.
2. **The invoice email was blocked by a NOT NULL outbox column** — before a tenant exists there was
   nothing to own the outbox row. The platform's own business now owns it.
3. **The invoice email was "skipped: channel_authorization_missing"** — a receipt is not marketing.
   `TRANSACTIONAL_KINDS` (`owner_alert`, `customer_invoice`) now bypass the opt-out, pause and
   channel-authorisation gates.
4. **A retried webhook could have emailed twice** — guarded by `emailed_at` and a per-invoice
   dedupe key.
5. **A provisioning failure would have lost the sale** — the invoice email is now unconditional, and
   the provisioning failure is recorded for a person to fix.

Tests: `tests/test_platform_billing.py` (17).
