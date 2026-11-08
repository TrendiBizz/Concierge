# Trendi Concierge

The current product uses the canonical FastAPI/PostgreSQL backend in `api/`,
the Rust social service in `concierge-stack/social-service/`, and the existing
Trendi marketing website in the sibling `trendi-site-web` repository. Customer
identity, knowledge, office pipeline, native bookings and tenant permissions are
handled by that backend.

## Run the integrated local product

Double-click **Start Trendi Local.command**. Open **http://127.0.0.1:8793/** for
the website or **http://127.0.0.1:8793/admin-ui** for the office dashboard. The
launcher copies the local admin key to the clipboard so you can paste it at sign-in.
Use **Add customer** to create a business and its private owner invitation.

This runs current source with separate persistent local data. It preserves existing
production, Twenty CRM, OAuth connections, voice and recording services. Local
publishing and outbound delivery stay disabled. Double-click **Stop Trendi
Local.command** to stop only the local stack and retain its data.

See [local runtime instructions and verification](scripts/local/README.md) for
architecture, source checks, repeatable smoke tests and external-provider limits.

## Legacy standalone module experiments

The material below describes earlier independent Node modules. They are retained
as source experiments, are not started by the integrated launcher, and do not define
the current product's identity, OAuth or booking behavior. Their separate databases
must not be treated as another canonical backend.

An independent, de-bloated alternative to GoHighLevel. Standalone: no GHL
dependency, no third-party dependency anywhere in any module. Each module
is its own small Node server (zero npm packages, built-in `node:sqlite`),
its own SQLite database, its own test suite, and its own vanilla-JS
dashboard -- built the same way on purpose, so they read the same and will
integrate the same way later.

## Modules

| Module | Folder | Port | What it does |
| --- | --- | --- | --- |
| Social | `/Users/jo/Pukeko/SocialSync/` | 4377 | Compose/schedule social posts, guardrails, manual publish (copy + open the platform) -- no OAuth, by design. Originally built for Pukeko Construction, now multi-tenant. |
| CRM | `crm/` | 4401 | Contacts, a simple editable-stage pipeline, opportunities. |
| Calendars | `calendars/` | 4402 | Recurring weekly availability windows, computed open slots, bookings with collision checking. |
| Payments | `payments/` | 4403 | Invoicing -- line items, computed totals, sequential numbering, status tracking. **No real payment processing.** |
| Sites | `sites/` | 4404 | Published pages (heading/paragraph/image/button/lead-form blocks), real public rendering, lead capture. |
| Workflows | `workflows/` | 4405 | Event-triggered automations -- log and real-webhook actions only. |

Run any module with `cd <module>/server && npm start`. Each needs Node 22.5+
and nothing else -- no `npm install` step, there are no dependencies.

## Tests

Every module has its own `node --test` suite (11-19 tests each), all
passing, and every one of them was also smoke-tested against a real running
server (not just the test harness) before being called done. Run them all:

```bash
for m in crm calendars payments sites workflows; do
  echo "== $m =="
  (cd "$m/server" && npm test)
done
(cd /Users/jo/Pukeko/SocialSync/server && npm test)
```

## Identity in the legacy modules

Every module has its OWN separate `tenants` table, own passcode, own
database file. Creating a customer in CRM does not create them in
Calendars, Payments, Sites, Workflows or Social -- these modules were tested
in isolation, but a customer of these older modules has to be created
once per module, with a different passcode each time. A central identity
service (one "create a customer" call that every module recognizes the
result of) is the real next step once this set of modules is confirmed to
be the right set -- deliberately not built yet, to avoid guessing its shape
before there was more than one module to integrate.

A second, related gap: nothing calls module-to-module yet. Sites capturing
a lead could fire Workflows' `lead.created` event automatically; Calendars
booking an appointment could do the same. None of that wiring exists --
every module works standalone and was proven to with its own smoke test,
but nothing connects them to each other yet.

## What was left out of the legacy experiments

Each module's own README has a "Deliberately not built" section specific to
it. The common thread: no OAuth/live third-party integrations (Social), no
real payment gateway (Payments), no visual drag-and-drop builders (Sites,
Workflows), no scheduled/cron triggers (Workflows), no multi-user-per-tenant
accounts (everywhere -- one shared passcode per tenant, today). These are
flagged choices, not oversights -- each module's README says why.
