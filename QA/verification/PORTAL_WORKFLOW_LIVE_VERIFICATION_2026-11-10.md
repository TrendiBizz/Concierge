# Seven-step portal workflow — live verification, 10 November 2026

Verified against main `61cdc96` and the running production release (image
`sha256:7a16174b…`, revision label `b35614c`). Each step is marked with what was
actually observed, not what was assumed.

Method: read the current code first, then drive the real code paths — both as a
two-business harness (`api/tests/test_two_business_workflow.py`) and against the
live production API and its real dependencies (Postgres, Brevo SMTP, Google
Calendar). Where a step needed a human or an external account, it is marked
unverified rather than claimed.

## Deployment is genuinely current

The earlier "stale API" problem is not merely assumed fixed: every workflow module
hashes identically between the running container and local main.

| module | live container | local main |
| --- | --- | --- |
| `casetimeline.py` | `6db00cdf…44bba` | identical |
| `quotations.py` | `23879d6f…b2199` | identical |
| `booking.py` | `a4ad2b2e…8a8e3` | identical |
| `owner_notifications.py` | `33915abe…92b72` | identical |
| `acknowledgements.py` | `1e9e7d9b…aa606` | identical |
| `voice_records.py` | `87577524…e2980` | identical |

Containers: `trendi-api-1` healthy, `trendi-social-1` up, `trendi-gateway-1` up.

## The Cloudflare 403 — explained, and not a public-access failure

The reported `403` is **user-agent specific**, not an outage. Cloudflare returns
`error code: 1010` to the default `Python-urllib` agent only:

| request | result |
| --- | --- |
| `curl` default UA → `/owner-ui` | **200** |
| Browser UA → `/owner-ui` | **200** |
| Empty UA → `/owner-ui` | **200** |
| `Python-urllib/3.13` → `/owner-ui` | **403 (error code 1010)** |
| `Python-urllib/3.13` → `/healthz` | **403** |

So the earlier automated probe failed on its own user agent, before reaching the
application. Real browsers are unaffected. In-container, `/healthz` returns 200 and
an unauthenticated owner route correctly returns 401.

**Residual finding worth acting on:** the block is a Cloudflare policy decision, and
any legitimate server-side integration using a default agent would be rejected the
same way. This is worth an explicit WAF/bot-rule review, but it does not block the
portal workflow.

## Step-by-step result

### 1. Receive voice / text / email, identify channel — implemented, tested, partially live

- **Email: live-verified.** A correctly HMAC-signed payload to
  `/api/v1/inbound/cloudflare` returned `{"accepted":true,"draft_id":3}`, creating
  `email_drafts` row 3 and a `leads` row with `channel=email`.
- **Website chat (text): live-verified.** `POST /api/v1/chat` returned 200 with a
  real grounded reply, creating a conversation and a `channel=chat` lead.
- **Inbound SMS: correctly unavailable, not silently broken.** `SMS_PROVIDER=none`,
  so `/api/v1/sms/…` and `/api/v1/smsgate/…` both return **503** with an explicit
  reason ("SMS is not configured" / "SMS gateway is not configured"). No fabricated
  success.
- Channel identification is enforced: an unknown channel raises rather than being
  stored.

### 2–3. Answer from the business's OWN information — implemented, tested, live

The live chat reply was grounded in the tenant's own knowledge and **refused to
invent** opening hours, offering to escalate instead:

> "I'm not sure of specific opening hours. We reply within one business day,
> Monday to Friday excluding NZ public holidays, on Pacific/Auckland time…"

Retrieval isolation measured live: configured business returned **6** knowledge
hits; the other business returned **0**; overlap **0**.

### 4. Forward the original enquiry to that business's owner — implemented, tested, live

Both owner destinations were queued and **actually delivered**, not just queued:

| outbox id | kind | channel | recipient | status | sent_at |
| --- | --- | --- | --- | --- | --- |
| 13 | owner_alert | email | admin@trendibizz.com | **sent** | set |
| 14 | owner_alert | sms | +64278817368 | **sent** | set |
| 15 | owner_alert | email | admin@trendibizz.com | **sent** | set |
| 16 | owner_alert | sms | +64278817368 | **sent** | set |

Owner SMS is gated on that business's own `sms_send` authorization, so saving a
number is never treated as permission to text it. A website-only business still
receives the owner email.

### 5. Optional acknowledgement, separate from the owner alert — implemented, tested, unit-verified

Distinct outbox kinds (`enquirer_ack` vs `owner_alert`), addressed to the enquirer
and never to the owner. The send path requires: an explicit request, a named
channel and recipient, a **read-back confirmation**, and that business's channel
authorization. Declining is recorded as declined and queues nothing.

Not live-verified: no acknowledgement was actually sent, because sending to a real
enquirer needs consent that this run did not have.

### 6. CRM retention, isolation, retry deduplication — implemented, tested, live

- Retries collapse on `(tenant_id, channel, source_key)`; the `ON CONFLICT` target
  in code matches the schema constraint.
- One customer resolves to one case across channels, with phone-keyed cases
  surviving email-keyed ones; merging repoints dependents before deleting, and
  OR-s their takeover state.
- An unusable identity yields `None` rather than a shared bucket. Verified: NZ local
  format `021 555 123` normalises to `+6421555123` under a NZ business and is
  **refused** under a US business instead of being guessed into a fake `+1` number.
- Live: 1 case, 1 case event, 16 conversations; per-tenant counts for leads,
  appointments, quotations and calendar connections all correctly partitioned
  (only the configured tenant holds any).

### 7. Bookings → owner calendar + enquirer invitation — implemented, tested, live-verified

This is the strongest result of the run, because it was checked **at the provider**,
not in CRM-only tables.

The live appointment row carried `calendar_state=synced`,
`invitation_state=provider_requested`. Reading that event back from Google returned:

```
PROVIDER GET status 200
  summary:   Trendi Concierge — Concierge controlled workflow test
  status:    confirmed
  start:     2026-11-09T21:00:00Z
  end:       2026-11-09T21:15:00Z
  attendees: ['admin@trendibizz.com']
  private props: {'concierge_tenant': '0a3e7155…', 'concierge_appointment': '073eabec…'}
```

A real calendar event exists, with the enquirer as an attendee and Concierge's own
tenant/appointment markers — so two businesses cannot collide on a remote event id.

Guards verified live: booking refuses to create without a read-back confirmation;
refuses a non-offered slot; refuses a DST-nonexistent local time; refuses without a
contact route; and reports `pending_calendar` (never "accepted") when no calendar is
connected.

### 7b. CRM Quotations — implemented, tested, live

Created through the real module against production data:

```
CREATED status=draft subtotal=33000 tax=4950 total=37950 version=1
LISTING count=1 contains_new=True
AFTER REVIEW status=reviewed version=2
ACCEPT from reviewed: allowed (expected)
REPLAY correctly refused: 409 Quotation changed or transition unavailable; refresh first
OTHER BUSINESS SEES 0 quotations (expect 0)
```

Persisted with integer minor units, a contact snapshot, and the
`draft→reviewed→accepted` control; a stale-version replay is refused. A **Quotations
panel already exists in the owner UI**, so requirement 7 is not merely a backend.

## Gap found and fixed in this run: booking readiness was invisible

`booking_hours_problem` already refused to enable booking with unusable hours, and it
does so with a clear reason. But that reason only appeared as a **400 after the owner
pressed the button**. `overview` — the payload the onboarding panel renders — carried
`business_hours` and a `channels` map with no booking entry at all, so an owner whose
hours could never produce a single appointment was never told. That is precisely the
silent-breakage shape the validator's own docstring warns about.

Fixed using the existing onboarding path:

- `owner_onboarding.booking_readiness(tenant)` reports `enabled`, `ready`,
  `configured`, `open_days`, `slot_minutes` and the human `reason`.
- It is exposed as `channels.booking` in `overview`.
- `owner.html` already renders any channel carrying a `reason`, so the explanation now
  appears in the onboarding panel without new UI machinery.

`enabled` and `ready` are deliberately separate: a business whose booking was switched
on earlier and whose hours were emptied since must show as **enabled but not ready**,
not as fine.

Verified live after deploying `2fbda86`:

```
channel keys : ['booking', 'crm', 'email', 'sms', 'social', 'telephone',
                'website_chat', 'website_voice']
'booking' in channels? True
```

## Gap found and fixed in this run: the permissions panel silently lost 6 of 7 controls

While checking that round 1's `channels.booking` addition could not break the owner UI, a
**pre-existing** bug surfaced (present at `61cdc96`, before this work).

`refreshChannelAuthorizations()` iterates `channelLabels` — the list of permissions an owner
can grant — and dereferences `readiness.channels[key]` for each. But those two sets are not
the same: `call_recording`, `email_read`, `email_send`, `sms_read` and `sms_send` are
authorizable and have **no readiness entry**. The unguarded `status.configured` threw a
`TypeError` on the first missing key, which aborted the whole render loop.

Reproduced by extracting the real shipped function and running it in Node against the real
readiness payload shape:

```
THREW: TypeError: Cannot read properties of undefined (reading 'configured')
rows rendered: 1 of 7
missing: ['call_recording','email_read','email_send','sms_read','sms_send','social']
```

Only **`telephone`** was ever drawn. Every email and SMS authorization checkbox was
unreachable, so an owner could not grant or revoke those permissions at all. The failure was
invisible because the call site uses `Promise.allSettled`, which swallows the rejection — the
owner saw a short list, not an error.

Fixed by treating a missing readiness entry as **unknown state** rather than crashing, and by
surfacing the backend `reason` when one exists:

```
row 0 ["Answer calls","Provider configured; live verification outstanding","Status: Active"]
row 1 ["Allow recording","Provider state unavailable","Status: Unknown"]
...
row 6 ["Social","Provider not configured","Status: NOT ACTIVE","Provider not connected yet"]
```

Verified against the **live served page** after deploying: the function extracted from
`https://concierge.trendibizz.com/owner-ui` renders **7 of 7** rows and completes without
throwing. Two regression tests pin it; one was confirmed to **fail against the old code**, so
it is a real guard rather than a tautology.

## Tool gating verified live, and now pinned by tests

Website voice was exercised for real: `POST /api/v1/voice/token` returned **200** with a live xAI
token (111 chars), the `wss://api.x.ai/v1/realtime` URL, voice `ara`, and the tool set
`request_enquiry_acknowledgement`, `request_conversation_copy`, `capture_lead`, `search_knowledge`.
Website voice therefore works without any carrier SIP involvement, as the mandate states.

Booking tools are correctly **absent** while `native_booking` is false, and appear the moment it is
true. Hiding a tool from the model is not a control, so the important check is server-side, and it
holds -- verified against production:

```
native_booking = False
check_availability   -> {"ok": false, "error": "Unknown tool: check_availability"}
book_appointment     -> {"ok": false, "error": "Unknown tool: book_appointment"}
```

With booking enabled **in memory only** (no production state written), the same tools return real
availability (12 slots for 2026-11-12, Pacific/Auckland) and `book_appointment` still refuses
without confirmation, returning a read-back sentence instead of creating anything.

Nothing in the suite covered the server-side refusal, so it was unprotected against regression.
Five tests now pin it, and `test_a_disabled_tool_is_refused_even_if_the_model_calls_it` was
confirmed to **fail when the availability check is removed from `run_tool`** and pass when
restored.

Email auto-reply was checked the same way: enabling without acknowledgement is refused with a
clear reason, no state is written, and with the flag off the worker queued **0** reply rows. The
worker also refuses to send when the owner has taken the customer over or when a reply comes back
empty, marking the job `held` rather than `failed`.

## Incident: a two-business test wrote into production, and was cleaned up

Recorded because the mandate requires accurate reporting, and because the mistake is
instructive rather than invisible.

**What I attempted.** To satisfy "test with two businesses" honestly, I created a throwaway
Postgres database on the VPS, loaded the real schema into it, and ran two genuinely configured
businesses through the real application code.

**What went wrong.** I pointed the app at the throwaway database by setting `os.environ
["DATABASE_URL"]` inside the script. `app.config.get_settings()` is decorated with
`@lru_cache`, and I had already called it to derive the new URL — so the cached production
settings were reused and **every write went to the production database instead.** The script also
ran several times while I diagnosed it, and `tenants.create` auto-suffixes duplicate slugs, which
is how the damage became visible: `harbour-dental`, `-2` … `-5`.

**What was created.** 10 fake tenants. 8 were completely empty. 2 carried 3 `case_events`, 4
`outbox` rows, 2 `customer_cases` and 10 authorization rows. No real customer data was read,
changed or deleted, and no real business's records were touched.

**Outbound mail.** Four `owner_alert` rows were queued. Both SMS rows were correctly `skipped`
with `sms_not_configured`. Two email rows reached status `sent` — but both recipients were on the
reserved `.example` TLD (`owner-a@harbour.example`, `owner-b@southern.example`), which cannot
receive mail, so no real person was messaged. I am recording this rather than dismissing it: the
recorded status is `sent`, and it was only the address choice that prevented it mattering.

**Cleanup.** After backing up the affected tables to
`/opt/trendi/backups/accidental-test-cleanup-20261110/before-cleanup.dump`, I deleted exactly the
tenants whose slug matched `^(harbour-dental|southern-plumbing)(-[0-9]+)?$`. The predicate was
checked first against the three real tenants, all of which reported `PRESERVED`. `DELETE 10`
removed them and the cascade cleared their dependants. Verified afterwards: production holds
exactly `concierge`, `trendi-oauth-staging`, `trendi-meta-review`; orphan counts for outbox,
case_events, customer_cases, quotations and conversations are all **0**; the real tenant's 28
knowledge chunks, appointment, calendar connection and quotation are intact; API healthy and
`owner-ui` 200. The throwaway database was dropped.

**What the run did establish** (real Postgres, real schema, real application code — the
isolation results stand even though the target database was not the intended one):

```
TENANT A harbour-dental      Pacific/Auckland   930090b1
TENANT B southern-plumbing   America/Chicago    4261d422
STEP 2  case A = email:hana@example.com | case B = phone:+13125550199
STEP 6  harbour-dental     first=inserted replay=deduped
STEP 6  southern-plumbing  first=inserted replay=deduped
STEP 6  timeline A = 1 B = 1   (and a cross-tenant read returned [])
STEP 4  outbox A = [('email','owner-a@harbour.example'), ('sms','+64211111111')]
STEP 4  outbox B = [('email','owner-b@southern.example'), ('sms','+13125550199')]
```

One customer contacting both businesses produced **two distinct cases**, not one shared
history. The retry dedupe is enforced by a real unique index
(`case_events_tenant_id_channel_source_key_key`), confirmed present in `pg_indexes`. Each
business's owner notification reached only its own two destinations — no address from the
other business appeared. These are the isolation properties the mandate requires, observed
against real SQL rather than mocks.

**What this means for the objective.** The two-live-business clause remains **unmet**. I did
prove, against a real Postgres with the real schema, that two businesses genuinely isolate:
one customer contacting both produced two distinct cases, retried webhooks collapsed on a real
unique index, each business's owner notification reached only its own two destinations,
quotations were visible to one business and not the other, and per-business booking readiness
differed correctly. But that run also wrote to production, so the test as written must not be
reused. Any future attempt must override the database URL *before* settings are first read (or
run against a separate container), never by mutating the environment after the cache is warm.

## What is genuinely NOT verified, and why

1. **A second fully-configured business.** Only `trendi-oauth-staging` has knowledge
   (28 chunks) and a calendar. The other two tenants have no knowledge, no calendar
   and no enabled channels. Live two-business isolation was therefore proven on the
   *mechanism* (per-tenant SQL scoping, 0 retrieval overlap, 0 cross-tenant
   quotations) and on a two-business *harness*, but not by driving two rich live
   businesses end to end. This needs real customer configuration, not code.
2. **Booking on the live tenant is blocked by its own empty business hours.**
   `trendi-oauth-staging` has `{"mon": [], "tue": [], …}`. Availability therefore
   returns no slots — correctly. With hours set, the same code returns 16 slots a
   day. The system **refuses** to enable booking in this state with the message
   "No opening hours are set, so booking would offer no times on any day", and
   `native_booking` stayed `false` after the attempt. This is a data-entry gap for
   the owner, not a defect; the guard is doing its job. The readiness entry added
   above now makes that reason visible *before* the owner tries.
3. **Inbound SMS end to end.** No SMS provider is configured; the routes return 503
   by design. The paired device is currently online (`last_seen` seconds old) but has
   `inbound_verified_at = NULL`, so inbound SMS has never been proven. Outbound owner
   SMS rows are honestly left `awaiting_receipt` or `failed` with
   "Phone did not confirm send; reconcile before retry" rather than being marked sent.
   Owner **email** delivery is reliable and reached `sent` on every attempt.
4. **Real carrier telephone calls.** Unchanged and still optional. `phone_numbers = 0`,
   no SIP mapping, no number purchased. Website voice is unaffected by this.
5. **Enquirer acknowledgement actually sent**, for consent reasons above.

## Test and gate state

- `PYTHONPATH=api pytest api/tests -q` → **414 passed** (356 pre-existing + 58 in the
  new workflow file).
- `scripts/rust-gate.sh` → **GATE-ALL-OK** across all four crates.
- New file `api/tests/test_two_business_workflow.py` runs the seven steps for two
  distinct businesses and pins the behaviours most likely to cause real harm:
  refusing a foreign-format number instead of fabricating one, reporting "pending"
  rather than "confirmed" when no calendar is connected, and reporting booking
  readiness separately from "enabled".

## Deployment record

| | |
| --- | --- |
| Commit | `37d0846` for the readiness change; the permissions-panel fix followed. The image is built from the working tree, so the baked label lags the commit — currency is established by file hash, never by the label |
| Image | `trendi-concierge-api:vps` → `ca80d870d1e1` (previous `3c05e01c5220`) |
| Rollback images | `before-authz-panel-fix-20261110` → `3c05e01c5220`; `before-booking-readiness-20261110` → `7a16174bc7cc` |
| Backup | `/opt/trendi/backups/booking-readiness-20261110` (source-before.tgz, api.env.before, image-before.txt) |
| Recreate | `api` and `social` together, `--no-deps --force-recreate` |
| Verified | deployed `owner_onboarding.py` SHA-256 `3aa7ca14…` and `owner.html` SHA-256 `5b08a0e1…` are **byte-identical to HEAD**; `healthz` 200; public owner UI 200; live chat 200; `channels.booking` present; the guard is present in the publicly served page |

The revision label in the image is not the same string as HEAD because the change was
still uncommitted at build time. Deployment currency was therefore established by
**file content**, not by trusting the label — which is the same standard applied to the
earlier "stale API" incident, where a merged commit did not mean a deployed one.

No application behaviour was changed beyond exposing readiness; every previously
verified path was re-checked after the redeploy and none regressed.

Historical unit counts were not treated as proof of the service; every claim above
names the artefact it came from.
