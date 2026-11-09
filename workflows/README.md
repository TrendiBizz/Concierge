# Concierge Workflows

Event-triggered automations. Part of Concierge, Jo's independent,
de-bloated alternative to GoHighLevel -- standalone, no GHL dependency, no
third-party dependency.

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API, the automation engine, and it serves the dashboard too. Node only, no npm packages (built-in `node:sqlite` and `fetch`). |
| `web/` | The dashboard (Workflows, Run history, a test-event sender). Vanilla JS, no framework, no build step. |

## Features

- **Trigger**: a workflow fires on one event type -- any string you choose, e.g. `lead.created`, `invoice.paid`, `appointment.booked`. Events are sent in with `POST /api/events {type, data}`.
- **Actions**, run in order, only two kinds exist:
  - **Log**: records a message, with `{{field}}` substituted from the event's data (e.g. `"New lead: {{name}}"`).
  - **Webhook**: a real HTTP POST of `{event, data}` to a URL you control. No fake success -- the test suite proves this against a real local HTTP receiver, and against a real connection failure.
- **Run history**: every firing is recorded with each action's result (ok/failed + detail), per workflow.
- A workflow can be turned on/off without deleting it.
- **Multi-tenant**: every Concierge customer is a tenant, fully isolated (own workflows, own runs, own events only ever reach its own workflows). Signing in is a single passcode -- no username, no GHL, no third party.

## Run it

Requires Node 22.5+ (built-in SQLite and fetch).

```bash
cd ~/Concierge/workflows/server
npm start
```

Open http://127.0.0.1:4405. First time, create a customer:

```bash
curl -X POST http://127.0.0.1:4405/api/tenants -H 'Content-Type: application/json' -d '{"name":"Acme Co"}'
```

That returns a passcode once -- use it to sign in at the dashboard, then use "Send a test event" to see a workflow fire.

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4405` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `workflows/data` | Where the database and the HMAC secret live. **Back this folder up.** |

**Security note.** Plain HTTP, meant for your own network, same posture as Concierge's other modules. Do not expose it to the internet as it is.

### Tests

```bash
cd ~/Concierge/workflows/server && npm test
```

11 tests: auth, tenant isolation, workflow/action validation, event matching (including non-matching and disabled-workflow cases), a real webhook call against a local test receiver, a real webhook failure against a closed port, run recording, deletion.

## Deliberately not built (de-bloated vs GHL's workflow builder, not an oversight)

- Email/SMS sending actions -- faking these without a real email/SMS provider would be worse than not having them. Use the webhook action to call a real email/SMS service you've set up, instead.
- Conditional branching, delays/wait steps, multi-step approval chains.
- A visual drag-and-drop workflow canvas -- workflows are edited as a name + trigger + ordered action list instead.
- Scheduled/recurring triggers (cron-style) -- only event-triggered for now.

## Next steps (not built yet)

- Shared identity with Concierge's other modules. This module, like CRM/Calendars/Payments/Sites, has its OWN separate `tenants` table and passcode.
- Live wiring from the other modules: nothing in CRM, Calendars, Payments or Sites calls `POST /api/events` yet -- e.g. Sites capturing a lead could fire `lead.created` here automatically, but that integration isn't built. Today, firing an event is a manual API call (or the dashboard's "Send a test event").
- Scheduled triggers, email/SMS action types backed by a real provider.
- HTTPS and an internet-reachable deployment.
