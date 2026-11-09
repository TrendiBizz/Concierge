# Concierge Payments

Invoicing with manual status tracking. Part of Concierge, Jo's independent,
de-bloated alternative to GoHighLevel -- standalone, no GHL dependency, no
third-party dependency.

## NO REAL PAYMENT PROCESSING

There is no Stripe, PayPal, or any payment gateway integration anywhere in
this module. "Mark as paid" is a manual button the tenant clicks after being
paid some other way (bank transfer, cash, a payment link sent outside this
system, whatever). This module only tracks status -- it does not move money
and cannot confirm a payment actually happened. Do not represent it to
customers as a payment processor.

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API and it also serves the web dashboard. Node only, no npm packages (built-in `node:sqlite`). |
| `web/` | The dashboard (invoice list + filter, new-invoice form). Vanilla JS, no framework, no build step. |

## Features

- **Invoices**: contact name/email (free text -- not linked to the CRM module's contact records yet, see "Next steps"), line items (description/quantity/unit price), an optional flat tax-rate percentage, an optional due date, notes.
- **Totals** are always computed from the current line items (subtotal, tax, total) -- never stored as a separately-editable number, so they can't drift from the items.
- **Sequential numbering** per tenant: INV-0001, INV-0002, ... never reused even if an invoice is deleted.
- **Status**: draft -> sent -> paid, or void from draft/sent. A non-draft invoice is locked (can't be edited or deleted -- void it instead to keep the record while killing it).
- **Multi-tenant**: every Concierge customer is a tenant, fully isolated. Signing in is a single passcode -- no username, no GHL, no third party.

## Run it

Requires Node 22.5+ (built-in SQLite).

```bash
cd ~/Concierge/payments/server
npm start
```

Open http://127.0.0.1:4403. First time, create a customer:

```bash
curl -X POST http://127.0.0.1:4403/api/tenants -H 'Content-Type: application/json' -d '{"name":"Acme Co"}'
```

That returns a passcode once -- use it to sign in at the dashboard.

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4403` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `payments/data` | Where the database and the HMAC secret live. **Back this folder up.** |

**Security note.** Plain HTTP, meant for your own network, same posture as Concierge's other modules. Do not expose it to the internet as it is.

### Tests

```bash
cd ~/Concierge/payments/server && npm test
```

12 tests: auth, tenant isolation, line-item validation, total computation, sequential numbering per tenant, status-transition rules, edit/delete locking.

## Deliberately not built (de-bloated vs GHL's payments suite, not an oversight)

- Any real payment gateway (Stripe, PayPal, etc). See the warning above.
- Recurring/subscription billing.
- A product catalog.
- Multi-currency.
- Tax beyond one flat percentage field per invoice (no per-item tax, no tax jurisdictions).

## Next steps (not built yet)

- Shared identity with Concierge's other modules. This module, like CRM and Calendars, has its OWN separate `tenants` table and passcode. A central identity/tenant service is the real next step once enough modules exist.
- Link an invoice's contact to a CRM contact record instead of free-text name/email.
- A real payment gateway integration, if and when that's actually wanted -- a deliberate, separate decision, not a default.
- HTTPS and an internet-reachable deployment.
