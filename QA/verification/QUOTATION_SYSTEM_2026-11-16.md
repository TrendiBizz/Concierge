# Quotation system — rebuild (2026-11-16)

## Why

The quotation feature was a title, some lines, a tax percentage and a printed page. Measured
against what a trades business actually sends a customer, it could not:

- discount a line, or a whole job, and still have the printed figures add up;
- say what unit a line is priced in (`each`, `m²`, hours) — only a bare quantity;
- quote someone who had not already raised an enquiry (a walk-in, a phone call);
- keep the terms it was sent with (editing the business-wide terms silently rewrote old quotes);
- tell "approved" apart from "delivered", so "sent" was a timestamp with no state, and the
  customer page still said the quote was awaiting review after it had been emailed;
- record who accepted a quote, only that it had been accepted;
- be edited at all from the Studio: the builder wrote a draft and then the UI offered no edit path.

The AI draft, the reference numbering, the validity date, the public accept/decline and the
invoice-on-acceptance were already right and were kept.

## What changed

**Schema** (`api/app/schema.sql`, all additive and defaulted):

- `discount_basis_points`, `discount_cents` on `quotations`; `discount_cents` on `invoices`.
- `terms` frozen per quote, `quote_date`, `viewed_at`, `accepted_by_name`, `accepted_note`.
- `lead_id` may now be null, so a quote can be written for a customer who never raised an enquiry.
- `sent` added to the status check; `(tenant_id, status, created_at)` indexed.

**Domain and API** (`api/app/quotations.py`):

- `calculate()` is pure and returns a `Totals` named tuple: line gross, line discount, net subtotal,
  job discount, tax on the discounted amount, total. Half-up at every step, and the printed parts
  always add up to the printed total.
- Endpoints added: `GET /{id}`, `POST /{id}/duplicate` (new reference, fresh validity, draft).
- `PUT /{id}` edits a draft with optimistic locking and no longer detaches the quote from its
  enquiry (the UI lost `lead_id` on edit; it is now carried).
- Lifecycle is explicit: draft → reviewed → sent → accepted/declined, plus void. `TRANSITIONS` +
  `can_transition()` are data, not a source-shaped assertion.
- `send` moves the quote to `sent`, honours an owner-written subject and message, states the
  validity date, and gives an explicit resend its own dedupe key (the first send is still
  idempotent per version).
- Marking a quote accepted by hand (a verbal yes) now issues the invoice, exactly as the public
  acceptance path does. Before this, "accepted" on the phone produced no bill.
- The customer page records `viewed_at` the first time it is opened, so "sent 3 days ago, never
  opened" is visible.
- Accepting records the customer's typed name.
- One document renderer (`document_html`) replaces the two drifting HTML strings used by the print
  view and the public page: letterhead, reference, quote date, valid-until, from/prepared-for
  blocks, GST/NZBN when present, per-line units and discounts, subtotal/discount/GST/total, deposit
  note, notes, frozen terms, print stylesheet. All customer text is escaped.

**Studio** (`web/portal/src/Quotes.tsx`, new; the old block is gone from `CrmQuotes.tsx`):

- A real builder: enquiry picker or free-standing customer, title, quote date, valid-until, line
  grid (description, qty, unit, unit price, line discount, live amount), catalogue picker, job
  discount, tax, currency, notes, per-quote terms, live totals panel.
- Actions per status: Edit → Review/approve → Send (subject + message) → Resend / View; duplicate
  as a new draft; preview the document; copy the customer link; void; confirm payment.
- Business details, terms and payment instructions moved behind one "Edit business details"
  panel instead of competing with the builder for the top of the page.
- The line row wraps (`flexWrap: 'wrap'`), because a fixed row was measured clipped at 358px once
  already — the regression test now guards the new file and also rejects `nowrap`.

## Proof

- `api/tests/test_quotations_system.py` — 25 tests: per-line and job discounts, tax on the
  discounted amount, half-up rounding, the printed parts reconciling, validation (customer
  required, validity order, units, discounts), the transition matrix, document content and
  escaping, money formatting, send lifecycle, resend key, and invoice-on-manual-acceptance.
- Updated to the new contract (behaviour, not source strings): `test_quote_documents.py`,
  `test_two_business_workflow.py`, `test_crawl_findings.py`, `test_crm_bulk_and_exports.py`.
- Mutation proofs (each watched go red, then restored):
  - tax computed on the undiscounted subtotal → `test_the_job_discount_comes_off_before_tax` fails;
  - the invoice-on-manual-acceptance block removed → `test_marking_a_quote_accepted_by_hand_still_issues_an_invoice` fails.
- Suite: **1402 passed, 19 skipped, 29 failed**. The 29 are the documented local-Postgres outage
  (HANDOFF item 34): every one raises `ConnectionRefusedError ('127.0.0.1', 55433)`, the same 29
  as before this change. Docker is not running on this machine, so the DB-backed subset could not
  be re-run.
- Portal: `npx tsc -b` clean, `npm run build` succeeds, `npm run lint` 0 errors.
- Document HTML parsed with `html.parser`: no unclosed or stray tags; `<td>` 23/23, `<tr>` 8/8.
- Schema is applied idempotently at API start (`db.init()` executes `schema.sql`), so the
  migration runs on restart; every statement is `IF NOT EXISTS` / defaulted.

## Deploy

Deployed with `scripts/vps/deploy-api.sh` and `scripts/vps/deploy-studio.sh`; live evidence in the
section below.
