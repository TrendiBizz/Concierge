# Concierge CRM

Contacts and a simple sales pipeline. Part of Concierge, Jo's independent,
de-bloated alternative to GoHighLevel -- standalone, no GHL dependency, no
third-party dependency.

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API and it also serves the web dashboard. Node only, no npm packages (built-in `node:sqlite`). |
| `web/` | The dashboard (Contacts, Pipeline board). Vanilla JS, no framework, no build step. |

## Features

- **Contacts**: name, email, phone, notes, tags. Search by name/email.
- **Pipeline**: one ordered list of stages per tenant (defaults to New / Contacted / Qualified / Won / Lost, fully editable). An opportunity's stage is stored by name, so renaming a stage never strands existing opportunities.
- **Opportunities**: title, dollar value, stage, notes, tied to one contact. Move between stages from the board.
- **Multi-tenant**: every Concierge customer is a tenant, fully isolated (own contacts, own stages, own opportunities). Signing in is a single passcode -- no username, no GHL, no third party.

## Run it

Requires Node 22.5+ (built-in SQLite).

```bash
cd ~/Concierge/crm/server
npm start
```

Open http://127.0.0.1:4401. First time, create a customer:

```bash
curl -X POST http://127.0.0.1:4401/api/tenants -H 'Content-Type: application/json' -d '{"name":"Acme Co"}'
```

That returns a passcode once -- use it to sign in at the dashboard.

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4401` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `crm/data` | Where the database and the HMAC secret live. **Back this folder up.** |

**Security note.** The server speaks plain HTTP and is meant for your own network, same posture as SocialSync. Do not expose it to the internet as it is.

### Tests

```bash
cd ~/Concierge/crm/server && npm test
```

13 tests: auth, tenant isolation, stages, contacts, opportunities.

## Deliberately not built (de-bloated vs GHL, not an oversight)

- Forms/surveys, automations/workflows, email/SMS sending, custom fields.
- Multiple pipelines per tenant.
- Reporting beyond the simple per-stage count + total shown on the board.
- Drag-and-drop on the board (stage move is a dropdown instead, v1).

## Next steps (not built yet)

- Shared identity with Concierge's other modules (SocialSync today has its own separate `tenants` table with the same shape but a different database file -- a tenant created here is not automatically known to SocialSync, or vice versa). A central identity/tenant service is the natural next step once more modules exist, so "create a customer" happens once, not per module.
- HTTPS and an internet-reachable deployment.
- Multiple users per tenant (today one shared passcode per tenant, same as SocialSync).
