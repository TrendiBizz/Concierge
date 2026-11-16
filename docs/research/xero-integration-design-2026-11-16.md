# Xero integration — our build design (2026-11-16)

Companion to the vendor-facts document `xero-integration-requirements-2026-11-16.md` (what Xero
requires, cited) and §4 M5 of `docs/WAVE_CRM_REPLACEMENT_PLAN_2026-11-16.md` (why it matters). This
file is **our** side: how it slots into this codebase, and what it must never do.

## Corrections the vendor research forced (read this first)

Five things I had assumed wrongly before reading Xero's own docs. Each is a real defect if coded the
obvious way:

1. **A default invoice is invisible to accounting.** `Status` omitted means `DRAFT`, and DRAFT
   creates **no journals** and cannot take a payment. Every invoice we push must be sent
   `AUTHORISED` explicitly. Sent invoices are then immutable in the ways that matter: no update once
   paid, part-paid, credit-noted or in a locked period — which is why our "correction = credit note
   + new invoice" rule in the table below is not a preference, it is the only legal path.
2. **`PUT /Payments` creates; `POST /Payments` only deletes/voids.** Writing `POST` to record a
   payment is the classic Xero integration bug; it is the exact opposite of REST habit.
3. **A credit note and its allocation are two calls, not one**, and the note must be `AUTHORISED`
   before it can be allocated.
4. **Scopes: `accounting.settings` is not optional.** Without it `/TaxRates`, `/Items` and
   `/Organisation` are unreachable — so GST mapping is impossible and certification checkpoints
   7–8 fail. The scope set is `offline_access accounting.contacts accounting.invoices
   accounting.payments accounting.settings`. Apps created on/after 2 Mar 2026 get **granular**
   scopes automatically, and broad scopes die in Sept 2027, so build against granular names now.
5. **The refresh token rotates on every use** (the old one dies; a 30-minute grace covers a failed
   write) and lives 60 days. That means refresh is a *write that can lose the connection*: it must
   be serialised per tenant — a `SELECT ... FOR UPDATE` on the connection row — or two concurrent
   syncs will race and permanently disconnect a chamber. This is the single most likely way this
   integration breaks in production.

Also now known and folded into the plan below: rate limits are **5 concurrent / 60 per minute /
1,000 per day per tenant** (5,000 on Core+), app-wide 10,000/min; `Idempotency-Key` applies to
POST/PUT/PATCH only, is cached 6 minutes, returns 400 if reused with a different body, and is
checked *after* rate limiting so retries still burn quota; webhooks must answer 2xx within **5
seconds**, retry every 15 minutes for 24 hours and are then **disabled**; and tax types must be read
per organisation from `/TaxRates` (AU `OUTPUT` 10% / `EXEMPTOUTPUT` / `BASEXCLUDED`; NZ `OUTPUT2`
15%) because invoices default to **Exclusive** line amounts.

**The commercial ceiling is the headline risk:** a new app starts on the free Starter tier with **5
tenant connections**, and each customer organisation may hold at most **5 uncertified apps across
all vendors**. An uncertified integration therefore stops scaling at around five chambers — unless
the org is already full, in which case it cannot connect at all. A **Custom Connection** (one org,
`$10/month` AUD, AU/NZ/UK/US, no review, excluded from the five-uncertified-app cap, works against
the free Demo Company) is the correct pilot vehicle precisely because it dodges both caps. Growing
past the pilot means Core (50 connections) or certification (Plus, 1,000) — a real review with a
security assessment, not a config change.

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

1. A **Xero developer account** and an app at developer.xero.com. **Two genuinely different
   decisions**, not one:
   - **Pilot** → create a **Custom Connection**: one organisation, `$10/month` AUD, AU/NZ/UK/US only,
     no review, does not consume the five-uncertified-app cap, and can be pointed at the free Demo
     Company while we build. This is the fast, cheap, correct first step.
   - **Product** → an **authorization-code flow app with `offline_access`**, one app serving many
     organisations. Free Starter covers **5 connections**; past that it is Core (50) or certified
     Plus (1,000) with a security assessment. Decide before the first five chambers sign, because
     the sixth cannot connect without it.
2. Register the **redirect URI** we will run (`https://<studio host>/owner/xero/callback` for the code
   flow; Custom Connections need no redirect) and put the **client id/secret in the secret
   directory** — never in git, never in the database.
3. A **Xero Demo Company** for development plus one real chamber's Xero for acceptance. Someone with
   admin rights on that org has to click "allow" once.
4. For the first chamber: are membership invoices **GST-inclusive or exclusive**, and which bank
   account receives payments (a payment can only be recorded against a payment-enabled account in
   their chart)?
5. Confirm we may read `/TaxRates` per org (it needs `accounting.settings`) rather than assuming one
   GST rate applies to every customer — an AU chamber at 10% and an NZ one at 15% share our code.

## What cannot be answered without a live Xero account

Twelve questions are listed at the end of the vendor requirements doc. The ones that would change
the code: whether DRAFT or AUTHORISED is the right default for a chamber that reviews invoices
before sending, how the org's chart maps our invoice lines to `AccountCode`, and whether the Demo
Company's tax rates match a real org's closely enough to test against.
