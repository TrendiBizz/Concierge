# N1 — Subscription billing lifecycle and Studio Billing tab (2026-11-21)

**Cause.** `platform_billing` handled only `checkout.session.completed`. A subscriber who cancelled in Stripe or whose
card declined stayed live forever; there were no Stripe IDs on `tenants`; Studio had no billing view; provisioning
failures were written into `privacy_requests`.

**Fix.** `api/app/subscription.py` (new) + schema (`tenants.stripe_customer_id/stripe_subscription_id/billing_status/
billing_grace_until/billing_period_end/billing_cancel_at_period_end`, `stripe_events`, `billing_events`,
`platform_invoices.stripe_invoice_id`).
- Webhooks: `invoice.paid` (renewal tax invoice, clears dunning, lifts a billing pause), `invoice.payment_failed`
  (grace period `BILLING_GRACE_DAYS`, default 7, owner emailed), `customer.subscription.updated/deleted`,
  `charge.refunded` (invoice marked refunded, operator told). Each event applied once (`stripe_events`); a failed
  handler releases the event so Stripe retries.
- Suspension reuses the owner pause switch with `paused_by='billing'`: leads are still captured; an owner's own pause is
  never lifted by billing; bank-transfer tenants (`billing_status='none'`) are never auto-suspended. Hourly sweep worker.
- Studio: "Billing and invoices" tab (status sentence, invoice list, Stripe Customer Portal button).
- Provisioning failures now go to `billing_events`, not `privacy_requests`.

**Proof.** `api/tests/test_n1_subscription.py` (12 tests, real Postgres): grace then pause, no grace extension,
renewal idempotent across retries and replays, owner pause survives payment, cancel-at-period-end then delete, refund,
failed-handler release, signed webhook route, status/portal endpoints and owner-only. Mutation check: widening the sweep
cutoff fails `test_payment_failed_starts_grace_and_sweep_pauses_only_after_it_ends`. Full suite green.

**Needs from Jo (shipped disabled until supplied).**
1. `STRIPE_SECRET_KEY` (restricted key with Billing Portal write) so the portal button works; without it the tab says to email us.
2. In the Stripe dashboard: activate the Customer Portal, and add the five event types above to the existing webhook endpoint
   `/webhooks/stripe` (it currently may send only `checkout.session.completed`).
3. Optional `BILLING_GRACE_DAYS`, `STRIPE_PORTAL_RETURN_URL`.
