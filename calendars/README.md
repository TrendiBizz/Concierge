# Concierge Calendars

One availability-window booking calendar per tenant. Part of Concierge,
Jo's independent, de-bloated alternative to GoHighLevel -- standalone, no
GHL dependency, no third-party dependency.

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API and it also serves the web dashboard. Node only, no npm packages (built-in `node:sqlite`). |
| `web/` | The dashboard (Book, Appointments, Availability). Vanilla JS, no framework, no build step. |

## Features

- **Availability windows**: a tenant defines recurring weekly windows (day of week + start time + end time + slot length in minutes). This is the ONLY calendar type.
- **Open slots**: given a date, the server computes every open slot from the windows that apply to that weekday, minus anything already booked. Slots in the past are never returned.
- **Appointments**: contact name/email/phone (free text -- not linked to the CRM module's contact records yet, see "Next steps"), start time, duration, status (booked / completed / cancelled), notes.
- Booking rejects a time outside any window (422) and a time that overlaps an existing non-cancelled appointment (409).
- **Multi-tenant**: every Concierge customer is a tenant, fully isolated (own windows, own appointments). Signing in is a single passcode -- no username, no GHL, no third party.

## Run it

Requires Node 22.5+ (built-in SQLite).

```bash
cd ~/Concierge/calendars/server
npm start
```

Open http://127.0.0.1:4402. First time, create a customer:

```bash
curl -X POST http://127.0.0.1:4402/api/tenants -H 'Content-Type: application/json' -d '{"name":"Acme Co"}'
```

That returns a passcode once -- use it to sign in at the dashboard.

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4402` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `calendars/data` | Where the database and the HMAC secret live. **Back this folder up.** |

**Security note.** Plain HTTP, meant for your own network, same posture as Concierge's other modules. Do not expose it to the internet as it is.

### Tests

```bash
cd ~/Concierge/calendars/server && npm test
```

13 tests: auth, tenant isolation, windows, slot computation, booking collisions, status transitions.

## Deliberately not built (de-bloated vs GHL, not an oversight)

- Round-robin / multi-staff routing -- one calendar per tenant, period.
- A public-facing booking page for customers to self-book.
- SMS/email reminders.
- Recurring appointment series.
- A visual week/month calendar grid in the dashboard -- the Book tab lists open slots as buttons for the chosen date instead.

## Known limitation (real, not silently ignored)

**No timezone handling.** Every time in this module is the server's own local time -- there is no timezone conversion anywhere. Fine while testing on one machine in one region; becomes a real problem the moment a tenant and their customer are in different timezones.

## Next steps (not built yet)

- Shared identity with Concierge's other modules. This module, like CRM and SocialSync, has its OWN separate `tenants` table and passcode. Creating a customer here does not create them anywhere else. A central identity/tenant service is the real next step once enough modules exist.
- Link an appointment's contact to a CRM contact record instead of free-text name/email/phone, once that integration is designed.
- Timezone support.
- HTTPS and an internet-reachable deployment.
