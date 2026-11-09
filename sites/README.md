# Concierge Sites

Simple published pages and the leads their forms capture. Part of
Concierge, Jo's independent, de-bloated alternative to GoHighLevel --
standalone, no GHL dependency, no third-party dependency.

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API, the public page renderer, and it serves the dashboard too. Node only, no npm packages (built-in `node:sqlite`). |
| `web/` | The dashboard (Pages, Leads, a block editor). Vanilla JS, no framework, no build step. |

## Features

- **Pages**: a title and a unique (per tenant) URL slug, draft or published.
- **Blocks**: a page's content is an ordered list of blocks -- heading, paragraph, image, button, or a lead-capture form (name/email/phone fields). Add, remove, reorder (up/down), edit, from the dashboard's block editor.
- **Public render**: a published page renders as real server-side HTML at `/site/<tenant-id>/<slug>` -- no client-side framework, no build step, works with JS disabled. A draft page 404s publicly; only the tenant can preview it (via the dashboard's authenticated edit view).
- **Leads**: submitting a page's form stores a lead (whatever fields that form asked for), visible in the dashboard, filterable by page.
- All user-supplied text is HTML-escaped in the public render -- a block's content can never inject a script tag or break out of the page.
- **Multi-tenant**: every Concierge customer is a tenant, fully isolated (own pages, own leads). Signing in is a single passcode -- no username, no GHL, no third party.

## Run it

Requires Node 22.5+ (built-in SQLite).

```bash
cd ~/Concierge/sites/server
npm start
```

Open http://127.0.0.1:4404. First time, create a customer:

```bash
curl -X POST http://127.0.0.1:4404/api/tenants -H 'Content-Type: application/json' -d '{"name":"Acme Co"}'
```

That returns a passcode once -- use it to sign in at the dashboard. A published page for that tenant is reachable at `http://127.0.0.1:4404/site/<tenant-id>/<slug>`.

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4404` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `sites/data` | Where the database and the HMAC secret live. **Back this folder up.** |

**Security note.** Plain HTTP, meant for your own network, same posture as Concierge's other modules. Do not expose it to the internet as it is -- a real "website" product needs its own domain and HTTPS, which is a deliberately separate step (see "Next steps").

### Tests

```bash
cd ~/Concierge/sites/server && npm test
```

12 tests: auth, tenant isolation, slug validation and uniqueness, block validation, draft-vs-published visibility, HTML-escaping (an explicit test that injected `<script>` never reaches the rendered page), public form submission and lead capture, page deletion.

## Deliberately not built (de-bloated vs GHL's Sites/funnel builder, not an oversight)

- A drag-and-drop visual page builder -- pages are edited as a list of typed blocks instead.
- Custom domains.
- A/B testing or split-testing variants.
- A page-template library.
- E-commerce (cart, checkout, products) -- that belongs with the Payments module, not here, and isn't built there either yet.
- Any automatic action on a new lead (email/SMS notification, workflow trigger) -- that is the Workflows module's job, kept separate on purpose.

## Next steps (not built yet)

- Shared identity with Concierge's other modules. This module, like CRM/Calendars/Payments, has its OWN separate `tenants` table and passcode.
- Wiring a page's lead-capture submissions into the CRM module as real contacts, once that integration is designed.
- HTTPS, a real domain, and an internet-reachable deployment -- required before any of this can actually face real visitors.
