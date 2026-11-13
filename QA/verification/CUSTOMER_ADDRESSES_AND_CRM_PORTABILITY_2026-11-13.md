# Multiple addresses, and not being locked into us — 2026-11-13

Operator decision: **drop Twenty, the Studio is the CRM**, and make provision now for a business
that already runs its own CRM.

## 1. Twenty retired

Snapshot first, then stopped — nothing deleted:

```
/opt/trendi/backups/crm-20261113/concierge-crm.dump   1.5 MB, pg_dump -Fc
/opt/trendi/backups/crm-pw-20261113/                  old password hash + the one I set
```

`trendi-crm{,-db,-redis,-worker}-1` stopped; 19 → **15 containers**. The compose `crm` profile is
left intact, so bringing it back is one command (`--profile crm up -d`), and the volumes were not
touched.

The healthcheck used to expect those four containers and `https://crm.trendibizz.com/`, so retiring
the CRM would have paged every five minutes about a decision we made on purpose. Removed from the
expected list, the URL list and the TLS list. Live now: **37 ok / 0 warn / 1 fail** (the known
`trendi-support: consent,mailbox`).

## 2. One customer, many addresses

Before this, a person had exactly one `primary_phone` and one `primary_email`. Someone who called
from a mobile and emailed from work looked like two different customers.

New table `customer_addresses`, identity is `(tenant_id, kind, value)` — an address belongs to
exactly one customer in a business. `reconcile()` now matches on **any** address ever seen, not just
the primary, and merges carry their addresses across without tripping the unique index. Existing
customers were backfilled on deploy: **14 addresses** on production from the existing cases.

Endpoints (owner session, `editor` to change):

```
GET    /owner/contacts/{case_key}/addresses
POST   /owner/contacts/{case_key}/addresses      {kind: phone|email, value, label}
DELETE /owner/contacts/{case_key}/addresses/{id}
```

Deliberate rules: an unknown address arriving alone is **not** assumed to be the same person
(guessing would merge strangers); once linked, any of their addresses resolves to them; an address
already belonging to another customer cannot be claimed; and the last address can never be removed,
because that customer would become unfindable.

## 3. Their own CRM

Two directions, both plain text and documented, so nobody is trapped:

```
GET  /owner/export/contacts?format=json|csv     every customer, every address
POST /owner/import/contacts                      {format: csv|json, data|contacts}
GET/POST/DELETE /owner/webhooks                  their endpoint + secret
POST /owner/webhooks/deliver                     retry anything queued
```

* **Export** — JSON for a CRM importer, CSV with **one row per address** for a spreadsheet.
* **Import** — tolerant of the headers other CRMs actually export (`Phone`/`Mobile`/`Telephone`,
  `Email`/`E-mail`/`Mail`, BOM tolerated). Idempotent: re-importing matches on known addresses and
  updates instead of duplicating. One bad row is skipped and reported, never abandoning the file.
* **Push** — when a new customer is created, an event is queued and POSTed to the tenant's endpoint
  as `{event, data, sent_at}` with `X-Concierge-Event` and `X-Concierge-Signature`
  (`sha256=` HMAC of the exact bytes). Failed deliveries stay queued, retry up to 5 times, and
  `last_error` is kept. Nothing is queued at all for a tenant with no endpoint configured.

## Proof

Unit + integration, `api/tests/test_customer_addresses.py` (3) and `api/tests/test_portability.py`
(9 + 3 DB). The DB tests run against a real `pgvector/pgvector:pg16`, and one starts a real HTTP
server to receive a real webhook.

```
api/tests/test_customer_addresses.py ......... 3 passed   (real Postgres)
api/tests/test_portability.py ................ 9 passed, 3 skipped without a DB
```

Every fix mutation-checked: removing the address-matching clause fails all three address tests;
reverting the payload fix fails the webhook test.

## Verified live, in production, with a real session

```
export json              : 200, count present
export csv               : 200, header "customer,case_key,kind,address,channels,last_seen"
import 2 customers       : {"contacts":2,"addresses":2,"skipped":[]}
import the same file     : {"contacts":2,...}   customers still 2 -- no duplicates
addresses for a customer : email:one@portability.test, phone:+64210001111
add a second email       : 3 addresses on one customer
webhook set / get / del  : all 200
```

The two test customers inserted into the review workspace were deleted afterwards.

## Not yet built

The **screens**: a Team tab (member list, role change, deactivate — the offboarding gap), and portal
UI for addresses, import/export and the CRM webhook. The API and the guarantees are in place; the
customer-facing surface is the next step.
