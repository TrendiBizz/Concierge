# Concierge lead bridge (website form -> Twenty CRM)

Zero-dependency Node 22.5+ server. The website contact form posts here; the bridge creates (or finds) the
person in Twenty and attaches the enquiry as a note. If the bridge is not running, the form falls back to
opening the visitor's email app, so no enquiry is lost.

## Run
1. Start Twenty: `cd .. && ./setup.sh && docker compose up -d` (http://localhost:3010).
2. Open http://localhost:3010, create the workspace, then Settings > APIs & Webhooks > create an API key.
3. Save the key in `bridge/.twenty-key` (gitignored): `umask 077; pbpaste > .twenty-key` after copying it.
4. `HOST=0.0.0.0 node server.js` (HOST=0.0.0.0 only if the site is viewed from another machine, e.g. a VM).

`POST /lead` JSON: `first_name, last_name, email, phone, company, message, plan, source` (email or phone required).
`GET /health` shows whether a key is configured. Honeypot field `website` must stay empty. 20 requests/minute per IP.
Responses: 200 `{ok,twenty_id,duplicate,note}`, 400 invalid input, 413 too large, 429 rate limited,
502 Twenty unreachable, 503 no/invalid key.

## Test
- `npm test`: 18 tests against a MOCK Twenty. These prove the bridge's own logic only.
- `./test/live.sh`: the real check. Needs Twenty running and the key saved. Posts a lead, posts it again
  (must be a duplicate), confirms exactly one person exists in Twenty, then deletes the test person.

## Known limits
- Twenty REST shapes are confirmed against a real Twenty 2.56.0 by `test/live.sh` (people create, duplicate lookup, notes and
  noteTargets via `targetPersonId`). Re-run it after upgrading Twenty. Notes are still best effort: a note failure never fails a lead.
- Non-NZ phone numbers are stored whole in E.164 form; only +64 numbers are split into country and national parts.
- `company` is accepted but not linked (Twenty companies are separate records).
