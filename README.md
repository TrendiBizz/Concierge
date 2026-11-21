# Trendi Concierge

The product uses the canonical FastAPI/PostgreSQL backend in `api/`, the Studio
portal in `web/portal/`, the Rust social service in `concierge-stack/social-service/`,
and the Trendi marketing website in `website/`. Customer identity, knowledge,
office pipeline, native bookings, paired-phone SMS, and tenant permissions are
handled by the `api/` backend.

## Local testing & deployment

See [AGENTS.md](AGENTS.md) and `docs/AGENTS_DETAIL.md` for canonical test and
deploy workflows:

```bash
# Start disposable local Postgres for tests
./scripts/dev/test-db.sh

# Run the API test suite
cd api && PYTHONPATH="$(cd .. && pwd)/QA/verification/shims" \
  TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
  pytest -q

# Run the website SEO gate
python3 scripts/seo/site_seo.py check
```

All production deploys go only through `scripts/vps/` (`deploy-api.sh`,
`deploy-site.sh`, `deploy-studio.sh`, `sync-tooling.sh`, `verify-deploy.sh`).

## Legacy standalone module experiments

The folders below (`crm/`, `calendars/`, `payments/`, `sites/`, `workflows/`)
are retained as earlier standalone Node/SQLite experiments. They are not part of
the production backend and do not define the current product's identity, OAuth,
or booking behavior.

| Module | Folder | Port | What it does |
| --- | --- | --- | --- |
| CRM | `crm/` | 4401 | Contacts, a simple editable-stage pipeline, opportunities. |
| Calendars | `calendars/` | 4402 | Recurring weekly availability windows, computed open slots, bookings with collision checking. |
| Payments | `payments/` | 4403 | Invoicing -- line items, computed totals, sequential numbering, status tracking. **No real payment processing.** |
| Sites | `sites/` | 4404 | Published pages (heading/paragraph/image/button/lead-form blocks), real public rendering, lead capture. |
| Workflows | `workflows/` | 4405 | Event-triggered automations -- log and real-webhook actions only. |

Run any legacy module with `cd <module>/server && npm start` (Node 22.5+, zero npm dependencies).

```bash
for m in crm calendars payments sites workflows; do
  echo "== $m =="
  (cd "$m/server" && npm test)
done
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
