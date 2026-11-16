# Xero integration — our build design (2026-11-16)

Companion to the vendor-facts document `xero-integration-requirements-2026-11-16.md` (what Xero
requires) and §4 M5 of `docs/WAVE_CRM_REPLACEMENT_PLAN_2026-11-16.md` (why it matters). This file is
**our** side: how it slots into this codebase, and what it must never do.

## The precedent to copy, not reinvent

`api/app/calendar_connection.py` already solves the hard part of this problem for Google Calendar:
OAuth callback, hashed single-use OAuth state (`calendar_oauth_states`), tokens held **on disk in
the mounted secret directory** rather than in the database ("Secrets remain in the mounted secret
directory, never in API responses, logs, tenant clones or event payloads"), and a refresh-on-demand
`access_token(tenant_id)` helper that refreshes 60 seconds before expiry.

Xero gets the same shape. That is not laziness — it is the second integration of the same kind, and
the second one is where you find out whether the first was a pattern or a one-off. Differences are
only in the endpoints, the scopes and the fact that Xero's refresh token rotates (which makes
"refresh" a write, not an idempotent read — see `xero_tokens` below).

## Modules to add

| File | Responsibility |
|---|---|
| `api/app/xero_connection.py` | "Connect Xero" OAuth flow, state mint/verify, token refresh + rotation, disconnect, tenant selection when one Xero login has several orgs, `/owner/xero` router |
| `api/app/xero_sync.py` | Push (member→contact, period→invoice, cancellation→credit note), pull (payments, invoice status), reconciliation, retry with backoff |
| `api/app/xero_webhooks.py` | Public receiver, HMAC signature verification, dedupe by event id, enqueue work, return fast |
| `api/app/xero_sync_queue.py` (or a table + worker tick) | Durable outbox so a Xero outage never loses a sync; the same discipline `outbox` already applies to messages |
| `api/tests/test_xero_*.py` | Contract tests against a fake Xero (below) |

## Schema additions

```sql
CREATE TABLE xero_connections (
  tenant_id      uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  xero_tenant_id text NOT NULL,               -- the org chosen after consent
  xero_tenant_name text NOT NULL DEFAULT '',
  scopes         text[] NOT NULL DEFAULT '{}',
  enabled        boolean NOT NULL DEFAULT true,
  last_sync_at   timestamptz,
  last_error     text NOT NULL DEFAULT '',
  connected_at   timestamptz NOT NULL DEFAULT now()
);
-- Tokens intentionally NOT here: they live in the secret directory, like the calendar tokens.

CREATE TABLE xero_object_map (            -- the two-way key; without it, replays duplicate
  tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  local_table text NOT NULL,               -- 'members' | 'invoices' | 'invoices_credit'
  local_id    uuid NOT NULL,
  xero_type   text NOT NULL,               -- 'Contact' | 'Invoice' | 'CreditNote' | 'Payment'
  xero_id     text NOT NULL,
  xero_number text NOT NULL DEFAULT '',
  synced_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, local_table, local_id, xero_type)
);

CREATE TABLE xero_sync_queue (
  id          bigserial PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  local_table text NOT NULL,
  local_id    uuid NOT NULL,
  operation   text NOT NULL CHECK (operation IN ('push','pull','reconcile')),
  attempts    int  NOT NULL DEFAULT 0,
  run_after   timestamptz NOT NULL DEFAULT now(),
  state       text NOT NULL DEFAULT 'pending'
              CHECK (state IN ('pending','running','done','failed','needs_reauth')),
  last_error  text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE xero_webhook_events (
  event_id   text PRIMARY KEY,             -- dedupe: Xero retries deliveries
  received_at timestamptz NOT NULL DEFAULT now(),
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  handled    boolean NOT NULL DEFAULT false
);
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS xero_invoice_id text;
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS xero_status text NOT NULL DEFAULT '';
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'quote'; -- 'membership' later
```

## Direction of truth, per object

The single biggest failure mode in accounting sync is two systems both believing they own the same
field. Decide once, in code:

| Object | Source of truth | Conflict rule |
|---|---|---|
| **Contact** (member org) | ours, except an explicit allow-list of fields edited in Xero (phone, address, VAT number) | field-level; never overwrite a Xero-edited field back to our older copy |
| **Invoice** we raise | ours until `AUTHORISED`/sent, then Xero's status wins | we never edit a sent invoice; corrections are credit note + new invoice |
| **Payment** | **Xero** | if Xero says paid, we reconcile and do not retry; a payment in our Stripe that Xero lacks gets pushed once, then flagged |
| **Credit note** | ours (created by us on cancellation) | idempotent by local cancellation id |
| **Nothing** | — | we never DELETE in Xero. Archive/cancel only — a bookkeeper's history is not ours to erase |

## Tax: the piece that will break first

This project has already been burned by tax being added at checkout when the price was advertised
as final (the 2026-11-16 pricing work). The same rule has to hold in invoices:

- Line items are sent with an explicit tax type (`OUTPUT2`-style GST codes) and explicit `LineAmountTypes`
  (`Inclusive` or `Exclusive`), never left to the Xero org's default.
- Whether our membership prices include tax must be a **per-membership-type flag** that flows to the
  invoice, not a global assumption — the pricing decision here was made for USD consumer prices and
  must not be inherited silently by a chamber's GST-inclusive membership pricing.
- Tax-exempt member (charity, overseas) is a first-class flag with a test, not a special case in an
  `if`.

## Testing strategy (offline, deterministic)

Xero cannot be called in CI. So:

1. **Fake Xero over httpx**: `MockTransport` returning recorded shapes for contacts/invoices/
   payments, plus 429 and 5xx cases. Tests assert request bodies field by field (tax type, line
   amounts, currency, reference) — this is where most integration bugs actually live.
2. **Webhook signature tests**: a valid signature is accepted once, a bad one is rejected, and a
   replayed `event_id` is a no-op.
3. **Reconciliation tests**: Xero-paid → local reconciles → second delivery does nothing; local-paid
   → push once; both-paid → no duplicate, flag for review.
4. **Mutation checks** per the repo's rule: delete the tax-type argument and the test must go red;
   remove the dedupe and the replay test must go red.
5. **One manual acceptance against a real Xero demo org** before shipping, recorded in
   `QA/verification/` — the only way to catch what the docs do not say.

## Ops and observability

- Health check `xero:connection`: connected, token refresh works, last successful sync age.
  `needs_reauth` must surface as a **warning with an owner action**, not a silent retry loop.
- Webhook endpoint returns 200 fast and does the work in the queue; a slow receiver gets retried and
  then disabled by Xero, which is easy to miss until sync stops.
- Every sync attempt logged with the local id, Xero id, operation and outcome — the reconciliation
  view is built from that log, not from guesswork.

## What Jo must do before M5 can start

1. A **Xero developer account** and an app at developer.xero.com (see the requirements doc for which
   app type). Decide: single-organisation *custom connection* for the pilot (no review) vs *public
   app* for selling to many chambers (review required).
2. Register the **redirect URI** we will run (e.g. `https://<studio host>/owner/xero/callback`) and
   give me the client id/secret by putting them in the secret directory (never in git).
3. A **Xero demo company** to test against, and ideally one real chamber's Xero as the pilot.
4. Confirm the membership invoices are **GST-inclusive or exclusive** for that chamber.
