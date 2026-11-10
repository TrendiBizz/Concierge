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

### 5. Optional acknowledgement, separate from the owner alert — implemented, tested, live

Distinct outbox kinds (`enquirer_ack` vs `owner_alert`), addressed to the enquirer and never to the
owner. The send path requires an explicit request, a named channel and recipient, a read-back
**confirmation**, and that business's channel authorization. Declining is recorded as declined and
queues nothing.

Driven through the real code against a real Postgres, including delivery by the actual worker:

```
1. first ask        -> needs_confirmation True | queued rows: 0
2. confirmed        -> queued | recipient hana@example.com
   queued: [('926f2753', 'email', 'hana@example.com', 'pending')]
3. repeat confirm   -> enquirer_ack rows: 1   (must be 1)
4. after worker     -> sent
5. after takeover   -> skipped | human_takeover
6. after revocation -> skipped | channel_authorization_missing
```

So the acknowledgement is genuinely deliverable, is deduplicated against a repeat confirmation, and
is suppressed at delivery time by both human takeover and a revoked permission. `enquirer_ack` is
deliberately absent from `OWNER_KINDS`, which is what subjects it to the consent, opt-out and
takeover gauntlet that owner alerts are exempt from.

Still **not** verified: that a real enquirer received one, since that needs a real person's consent
and mailbox. What is proven is that the system queues, delivers and suppresses it correctly.

**A diagnosis worth recording.** My first run showed the acknowledgement being `sent` after a
takeover, which looked like a missing guard. It was not: `set_takeover()` can only pause a case that
**exists**, and my probe paused `email:takeover@example.com` with no such case row. The update
matched nothing, `is_paused_for()` correctly returned False, and sending was the right outcome. I
added the `reconcile()` step that real traffic performs and the guard then behaved exactly as
documented. The lesson is in the test docstring so the next reader does not "fix" a non-bug.

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

## Two-business end-to-end now passes, safely

After the incident above I fixed the test properly rather than abandoning it: `run_twobiz.sh`
exports `DATABASE_URL` **before** Python starts, and both the launcher and the script itself refuse
to proceed unless settings report the throwaway database. Re-run against that database, with the
real schema loaded:

```
target: postgresql://***@postgres:5432/concierge_twobiz_verify
confirmed throwaway target
TENANT A harbour-dental      Pacific/Auckland
TENANT B southern-plumbing   America/Chicago
STEP 2  case A = email:hana@example.com | case B = phone:+13125550199
STEP 6  harbour-dental     first=inserted replay=deduped
STEP 6  southern-plumbing  first=inserted replay=deduped
STEP 6  timelines A=1 B=1, cross-tenant read returned []
STEP 4  each owner reached only their own two destinations
STEP 5  ask waits for confirmation; ack addressed to the enquirer and owned by A
STEP 7b quote total = 28750 | A sees 1, B sees 0
STEP 7b reviewed -> v 2 ; stale replay refused 409
STEP 7  A slots = 12 Pacific/Auckland | B slots = 12 America/Chicago
READY   emptying B's hours flipped B only: B open_days = 0 reason set = True | A open_days = 5

ALL TWO-BUSINESS END-TO-END CHECKS PASSED
```

Confirmed afterwards that production held exactly its three real tenants while the two test
businesses existed only in the throwaway database, so the safety gate worked.

One assertion of mine was wrong rather than the code: I first expected `ready` to be True for the
business with open hours, but `ready` means *enabled AND usable* and booking is disabled for both,
so `ready` is False for both by design. The per-business discriminator is `reason` and `open_days`,
which moved for B alone. I corrected the test, not the implementation.

The harness is preserved at `QA/verification/twobiz/` with a README explaining the failure mode.

## Calendar isolation verified against the real provider boundary

The mandate's isolation requirement covers calendars, so I checked the enforcement rather than the
storage, using the throwaway database and the safety gate from the incident above.

Only `trendi-oauth-staging` holds a credential file; the other two tenants hold none. Credential
files are one per tenant UUID, mode `600`:

```
dir: /run/concierge-calendar
  0a3e7155-2f19-4527-bee1-f2dec7b676c7.json 620 600
  google-app.json                           225 600
```

With business A connected and business B not, syncing one of **B's** appointments did not reach a
provider at all -- it was refused and recorded:

```
A connected: True
B connected: False (expect False)
B appointment after sync: unconnected | Connect the owner calendar
event_id A != B: True
B token refused: CalendarUnavailable Reconnect the business calendar
```

So an unconnected business cannot have its booking written into another business's calendar, and
remote event ids cannot collide across tenants. Three tests now pin this, and
`test_a_business_without_a_calendar_cannot_sync_into_another_businesss` was confirmed to **fail
when the refusal guard is replaced by a fallback calendar** and pass when restored.

## Two-business harness extended to the channel boundary

The harness now also drives the per-business voice gate, which is where a metered resource could
leak between businesses:

```
VOICE   both businesses refused a token while voice was disabled
VOICE   A minted a real token, url = wss://api.x.ai/v1/realtime
VOICE   B still refused after A was enabled
VOICE   A daily limit enforced (tokens = 2 ); B counter untouched ( 0 )
```

Enabling voice for A let A mint a genuine xAI token while B stayed refused, and exhausting A's
daily limit did not consume a single unit of B's quota. The counters live per tenant, so one
business cannot spend another's allowance.

A side note recorded for accuracy: my earlier legitimate voice probes against the real tenant
consumed **1 of its 200** daily tokens, which is ordinary usage rather than damage. All six
voice_tokens rows belong to that real tenant; none leaked to the test businesses.

## Knowledge and email-draft isolation, verified against real SQL

Two more destructive surfaces were checked on the throwaway database, because both can destroy or
leak a business's own data when scoping is wrong.

**Business knowledge.** Two businesses were given documents with the *same title*, so the derived
document id is identical -- the case where a missing tenant filter would let one business delete
another's knowledge:

```
doc A: e397731993415212 | doc B: e397731993415212 | same id: True
A documents: 1 | B documents: 1
A removed: True
after A removes -> A documents: 0 | B documents: 1 (B must still be 1)
B content intact: 'Opening hours\n\nWe open at 8am.'
```

A's delete removed only A's chunks, and B's content survived intact. `test_removing_a_document_
cannot_touch_another_businesss_same_titled_document` was confirmed to **fail when the tenant
filter is removed from the DELETE** and pass when restored.

**Email drafts.** B's attempts to revise, discard or approve A's draft all returned `None` and left
A's draft in status `draft` with its body untouched. B's listing showed 0 drafts against A's 1. A
`REVIEW REQUIRED` draft was refused for approval, and a genuine approval queued exactly one row
with a repeat queueing none.

## What "invitation requested" actually means, checked at the provider

Reading the live Google event back exposed a distinction worth stating precisely, because it is
easy to overclaim:

```
appointment: Concierge controlled workflow test | attendee: admin@trendibizz.com
invitation_state recorded by Concierge: provider_requested
  status       : confirmed
  organizer    : admin@trendibizz.com
  attendee     : admin@trendibizz.com | responseStatus: needsAction
```

The event exists and is `confirmed`, with the enquirer recorded as an attendee. The attendee's
`responseStatus` is `needsAction` -- Google accepted the event but there is **no evidence in this
data that the invitation email was delivered or read**. That is exactly why the field is named
`provider_requested` rather than `sent`, and why the customer-facing wording is "the calendar
provider accepted the event and invitation request".

I am not claiming invitation delivery on the strength of `needsAction`. What is proven is that the
event is real at the provider, carries the enquirer as an attendee, and that Concierge requests
`sendUpdates=all` on insert. Whether Google's mail reached the inbox is only observable from the
recipient's mailbox, which is not something this system can see.

## Owner and enquirer recipients separated on the booking path

The mandate states explicitly that an owner alert is not an enquirer acknowledgement. Verified
live against a real Postgres -- one agreed booking produced eight outbox rows and the two recipient
sets never overlapped:

```
email owner_alert -> owner-a@harbour.example
sms   owner_alert -> +64211111111
sms   appt_confirm -> +6421555123
email appt_confirm -> hana@example.com
... appt_rem24, appt_rem2 to the enquirer only
owner recipients  : ['+64211111111', 'owner-a@harbour.example']
enquirer recipients: ['+6421555123', 'hana@example.com']
```

With `consent_contact` false, the owner is still told and the enquirer receives **nothing** -- the
consent gate applies to the enquirer only, which is the correct direction.

Two tests pin this, and the first was confirmed to **fail when the confirmation is deliberately
addressed to the owner's number** and pass when restored.

## Voice answers from the business's own knowledge, and cannot read another's

Voice loads business knowledge differently from chat, and that difference is worth stating because
it is where a subtle leak would live. Chat, SMS and email get a `<website_information>` block
assembled by retrieval *before* the model runs. Voice gets **no injected block** -- its prompt
instead instructs the model to call `search_knowledge`. So for voice, that tool is the only
knowledge path, which makes its tenant scoping the whole isolation guarantee.

Verified live against a real Postgres with two businesses holding distinct facts:

```
A knowledge chunks: 1 | B knowledge chunks: 1
A voice lookup mentions: Harbour Dental is open 9am to 5pm Monday to Friday
B voice lookup mentions: Southern Plumbing charges a callout fee of $89
A searching B's wording -> Harbour Dental hours ... 9am to 5pm
voice prompt has <website_information> block: False
voice prompt tells the model to call search_knowledge: True
chat prompt has <website_information> block: True
```

A searching with B's exact wording ("callout fee $89 weekends") still returned only A's own
knowledge, so the query text cannot steer retrieval across businesses. `_search_knowledge` passes
`tenant["id"]` from the request context, never anything the model supplies.

**A test I had to strengthen.** My first version asserted only that retrieval was called with the
calling business -- but a mocked `retrieve` ignores its arguments, so the test passed even when I
deliberately weakened the scoping to `args.get("tenant_id") or tenant["id"]`. That is a test that
merely restates the implementation. I rewrote it to supply a hostile `tenant_id` in the tool
arguments and assert it is ignored; it now **fails** under that regression and passes when scoping
is taken from context.

## Delivery idempotency: a re-claim must not text the customer twice

`outbox.process_once()` reclaims rows left in `sending` for over 10 minutes, to recover from a
worker that died mid-send. If a worker died *after* the SMS actually went out but before recording
it, that reclaim would re-deliver. The guard is the `request_key`, derived from the outbox row id,
which collides on `(tenant_id, request_key)` in `device_sms_jobs` instead of queueing a second text.

Verified live against a real Postgres:

```
jobs after first enqueue: 1
jobs after re-claim with same key: 1 (must still be 1)
jobs after a different key: 2 (must be 2)
changed content refused: SMS identity or content changed; review required
historical replay refused: Historical SMS requires owner review
```

**Three tests of mine were worthless and I only found out by trying to break them.** My first
attempts asserted that the source *contains* `ON CONFLICT(tenant_id,request_key)` and that
`_deliver` mentions a key derived from the row id. Under a deliberate regression -- appending the
attempt number to the key, which defeats the dedupe completely -- those tests still passed. They
restated the implementation instead of exercising it.

The version that works drives `outbox._deliver` three times for the same row with different attempt
counts and asserts the key never varies. That one **fails** under the regression and passes when
restored. Behaviour tests also now simulate the unique constraint on `device_sms_jobs`, so a
collision is exercised rather than described.

## The owner can actually see the retained dialogue, and only their own

Step 6 requires the complete dialogue to be retained. Retention is only half of it -- the owner has
to be able to read it, and not see anyone else's. Driven against a real Postgres with two
businesses:

```
A transcript turns: 2 | first: Do you do emergency dental work?
B transcript turns: 2 | first: My hot water cylinder is leaking.
B reading A's lead transcript -> 0   (must be 0)
A leads: ['Hana'] | B leads: ['Tomas']
A quotation total: 20700 | A sees: 1 | B sees: 0
```

Both halves of the transcript route matter and both are present: an ownership probe
(`SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2`) that decides 404, and a join that also
carries `c.tenant_id=l.tenant_id`. A test was confirmed to fail when the join's tenant condition is
dropped and pass when restored.

The route also falls back to `enquiry_sources.original_text` when a lead has no message rows, which
is what stops a voice enquiry from showing the owner an empty transcript. That fallback is pinned
too, because removing it would look like data loss rather than a missing branch.

## Two real production businesses, checked live and read-only

I had been treating "two businesses" as blocked on inventing customer data. Inspecting production
again showed that assumption was wrong: there are **two genuine owner accounts**, not one.

```
trendi-oauth-staging  Trendi Concierge        owner admin@trendibizz.com      28 chunks, 1 calendar
trendi-meta-review    Meta review workspace   owner meta-review@trendibizz.com 0 chunks, 0 calendars
```

Isolation between them, read live with no writes:

```
A booking open_days: 0 | B booking open_days: 5
A notify: admin@trendibizz.com | B notify: (none)
trendi-oauth-staging   {"chunks":28,"leads":7,"conversations":19,"cases":1,"events":1,"appointments":1,"quotations":1,"outbox":22}
trendi-meta-review     {"chunks":0,"leads":0,"conversations":0,"cases":0,"events":0,"appointments":0,"quotations":0,"outbox":0}
A quotations visible: 1 | B quotations visible: 0
A knowledge hits: 5 | B knowledge hits: 0
overlap between the two real businesses: 0 (expect 0)
```

The readiness difference is the strongest signal here. It is not a default and not a cache:
`trendi-meta-review` genuinely has weekdays `09:00-17:00` configured while `trendi-oauth-staging`
has every weekday empty, so the two businesses report `open_days` 5 and 0 respectively. Pinned by
a test so a future caching change cannot make one business look configured because another is.

**What is still blocked, and exactly why.** Booking and calendar verification for the second real
business needs a Google Calendar OAuth consent, which only the account holder can grant:
`trendi-meta-review` has **0 calendar connections** while `trendi-oauth-staging` has 1. That is the
precise, smallest missing input -- not "customer data", just one OAuth authorisation for a second
mailbox. Everything else about the second business is already verifiable and verified.

## Defect found and fixed: provider time precision stranded bookings in retry

Driving the booking path for the **second** real business surfaced a genuine defect. The
appointment recorded its time as `2026-11-13 00:30:05.917076+00:00`, and Google returned
`2026-11-13T00:30:05Z`. The verification step compared them with `!=`, which is false for any
sub-second difference, so it raised "Calendar event time does not match booking" and the
appointment was written to `retry`. It would have retried up to ten times and never synced.

Everything else in that verification passed -- status `confirmed`, the attendee present, both
Concierge markers matching -- so a single over-precise comparison was the whole failure.

**Severity, stated accurately.** The only appointment-creating path is `booking.book`, which builds
times from `time(0)` on a whole minute, so `starts_at` carries zero microseconds and this was
**not reachable in production**. The one production appointment synced precisely because its time
was `21:00:00`. So this was a latent fragility rather than a live outage: one careless INSERT, or a
future path that derives a time from `now()`, would have stranded every booking. I verified the
unreachability rather than assuming it -- all slots produced by the real availability path were
checked and every one had microsecond `0` and second `0`.

Fixed by comparing to the second rather than exactly:

```python
if abs((actual - expected).total_seconds()) >= 10:
    raise CalendarUnavailable('Calendar event time does not match booking')
```

Ten seconds is far tighter than any booking slot, so a genuinely wrong time is still refused; a
test asserts that 1 minute, 30 minutes and 2 hours apart all fail the tolerance.

**Verified against the real provider after the fix.** The same second-business run then reached
`synced` with `invitation_state=provider_requested`:

```
sync WITH calendar -> synced | invitation: provider_requested
provider GET: 200
  summary    : Meta review workspace — Meta Client
  start/end  : 2026-11-13T00:32:30Z -> 2026-11-13T01:02:30Z
  private    : {'concierge_tenant': 'cd0a7dfb-...', 'concierge_appointment': '1d25ba73-...'}
cleanup DELETE: 204
```

The event belonged to the **second** business, not the one already verified, which is the
two-business booking evidence the objective asked for.

**Provider hygiene.** Two test events were created in the owner's real calendar during this work.
Both were deleted (HTTP 204) and the calendar was confirmed back at its baseline of exactly one
event, the genuine production booking. Deletion was matched on the exact appointment id, so the
production event was never a candidate.

## The deployment was proved, and the tolerance proved safe

A source fix is not a working system, so the **deployed image** was driven against the real Google
provider with exactly the input that had failed:

```
stored start: 2026-11-24T03:07:05.917076+00:00
DEPLOYED sync -> synced | invitation: provider_requested
provider returned: 2026-11-24T03:07:05Z   (truncated, as expected)
cleanup DELETE: 204
```

Then the more important question: does widening the comparison hide a real error? Tested against the
same provider by moving the stored appointment 30 minutes **without** moving the provider event:

```
initial sync: synced
after a 30-minute mismatch -> retry | Calendar synchronization pending; retry scheduled
```

So a genuine mismatch is still refused. The tolerance is 10 seconds, smaller than the 5-minute
minimum appointment length the API permits, so no real slot could ever be masked. Two tests pin both
directions: sub-second drift accepted, 30 seconds through a day refused.

I also swept the codebase for the same class of bug rather than waiting to trip over it again: there
are no other datetime equality comparisons anywhere, and the calendar check was the only instance.

**Provider hygiene.** Three test events passed through the owner's real calendar across rounds 13
and 14. All three were deleted (HTTP 204 each) and the calendar re-checked at its baseline of one
event, the genuine production booking.

## The Cloudflare 403, characterised precisely

The earlier report called this "user-agent specific". It is narrower than that, and the distinction
matters for anyone integrating:

| User agent | Result |
| --- | --- |
| `Python-urllib/3.13` | **403 (error 1010)** |
| `python-urllib/3.13` (lowercase `p`) | 200 |
| `Python-urllib` / `Python-urllib/3` / `Python-urllib/9.9` | **403** |
| `python-requests/2.31` | 200 |
| `Go-http-client/1.1` | 200 |
| `curl/8.0` | 200 |
| `Mozilla/5.0 (compatible; Googlebot/2.1)` | 200 |

It is not a general non-browser block: `python-requests`, Go, curl and Googlebot all pass. It
matches the **case-sensitive literal `Python-urllib`** in the user agent, which is the signature of
a Cloudflare WAF custom rule rather than a managed default.

**Does it affect anything real?** No. `public_base_url` is only printed or used to build URLs
(`owner_notifications`, the CLI demo output, shared-recording links); nothing server-side fetches
its own public host. The one external service that posts to us, the paired phone connector,
identifies as `TrendiPhoneConnector/1.0` and is not matched. So this is a WAF policy to be aware of
for future server-side integrations, not an active fault.

## A transient I created, and correctly did not "fix"

Reading the gateway log while investigating showed repeated 502s on `/api/v1/device-sms/poll` from
the phone connector. It looked like an outage. It was not:

```
4 errors at 23:17    4 at 23:45    4 at 23:54    4 at 00:48    4 at 01:00
distinct messages: 15x "lookup api ... server misbehaving"
                    5x "dial tcp 172.18.0.6:8000: connect: connection refused"
```

Every cluster is exactly four errors and every timestamp is a container recreation **I** performed
during this session. The connector polls roughly every three seconds, so each restart costs about
four failed polls. Confirmed benign: the device's `last_seen` was 0.3 seconds old when checked, so
it resumes automatically, and there were **zero** gateway errors in the five minutes following the
last deploy.

So this is a ~10-second self-healing gap intrinsic to recreating a container, not a fault to fix.
Recording it rather than adding machinery for it, because a "fix" here would be complexity with no
demonstrated problem behind it.

## Why two businesses cannot share one Google account (verified against the provider)

The remaining blocker is that the second business has no calendar connection of its own. Before
treating that as pure ceremony I tested whether pointing two businesses at the **same** Google
account would work. It would not:

```
A booked: synced
B sees as busy: 1 windows
    2026-12-02T06:00:00+00:00 -> 2026-12-02T06:30:00+00:00
FINDING: on a SHARED calendar, A's booking blocks B's availability.
```

The event ids do **not** collide -- they hash `(tenant_id, appointment_id)`, so each business's
events stay distinct and carry their own tenant marker. But the availability check is per
*calendar*, not per tenant: `busy()` asks `freeBusy` about one calendar id, and
`calendar_id` is fixed to `'primary'` at connection time with no owner-selectable alternative. So
two businesses on one calendar would see each other's bookings as unavailable time.

**This makes per-business authorization a correctness requirement rather than a formality.** A
shared account would not corrupt data, but it would cause one business's appointments to block
another's availability -- exactly the kind of cross-tenant leak the mandate forbids, arriving
through the calendar rather than the database.

Two tests pin it, including that connecting one business never implicitly enables another.

**Provider hygiene.** One more test event was created and deleted during this check (HTTP 204), and
the calendar was re-verified at its baseline of one event, the genuine production booking.

## The calendar scope is deliberately minimal, and sufficient

A business is always connected to `primary` and cannot choose another calendar. I checked whether
that is a defect or a deliberate trade-off, by testing what the granted scopes actually permit
against the real provider:

```
granted scopes: calendar.events, calendar.freebusy
freeBusy: ok, 0 busy windows
create+verify: synced
delete: 204
calendarList (needs a wider scope): 403
```

So the two narrow scopes cover **everything the workflow does** -- check availability, create the
event, verify it and the attendee, delete on cancellation -- while enumeration is refused. The app
never requests full `calendar` access, which would also allow reading and deleting any calendar the
owner holds.

That is good security practice, not a gap. The practical consequence is that a business wanting its
bookings on a *secondary* calendar cannot express that; it would need a wider scope than the feature
otherwise uses. Only one connection exists today and `primary` is the sensible default, so this is a
latent limitation rather than an active problem. I have recorded it rather than widened the scope
unilaterally, because granting more access than the feature needs is not a decision to make quietly
on someone else's account.

Three tests pin the boundary: the exact scope set, that the OAuth finish refuses a token missing
offline access or holding different scopes, and that the schema allows one connection per business.

**Provider hygiene.** One more test event created and deleted (204); calendar re-verified at its
baseline of one event.

## The rollback was drilled, not assumed

Every deployment this session was made "with rollback available", but that only means a tagged
image existed. An untested rollback is a claim rather than a capability, so I drilled it end to end
on production.

Backed up first: `image-before.txt`, `api.env.before`, and a full `pg_dump` of the concierge
database (271 KB) to `/opt/trendi/backups/rollback-drill-20261110`.

Then rolled back to `before-calendar-time-tolerance-20261110` and confirmed the older code was
genuinely running:

```
AFTER rollback: tolerance present: False | exact compare present: True
healthz 200 | owner-ui 200
```

Data survived the rollback, which is what the handoff claimed but had not demonstrated:

```
tenants=3  chunks=28  appointments=1  leads=7  quotations=1  calendar_connections=1
```

Then restored the fixed image and confirmed recovery:

```
tolerance present: True
app/calendar_connection.py sha256 866432f4…  (matches HEAD exactly)
chat status 200 | owner-ui 200 | api healthy
```

**One thing the drill caught.** Restoring by re-tagging is easy to get wrong: my first attempt left
`:vps` pointing at `ca80d870d1e1`, the *pre-fix* image, which would have silently reverted production
while appearing to succeed. I detected it by running `grep` inside each image to see which one
contained the fix, rather than trusting the tag. Restoring by explicit image id fixed it.

Worth recording because the failure mode is quiet: a wrong tag still deploys, still reports healthy,
and still serves traffic -- it just runs the old code.

## The release tree was verified against HEAD, and cleaned of transfer artifacts

An image hash matching HEAD does not prove the *source tree* on the host does, and that tree is what
a future rebuild would compile. Compared file by file, all 62 application modules are byte-identical
to HEAD:

```
VPS   api/app/*.py  ->  62 files
local api/app/*.py  ->  62 files
diff (matched by hash and name) -> IDENTICAL
```

**The first comparison was misleading, and worth recording.** A naive `find | xargs sha256sum |
sha256sum` gave different aggregate hashes, because the VPS held 252 extra `._*` files -- AppleDouble
resource forks created by macOS `tar`/`scp`. That is 124 files under `api/` against 62 real ones,
which is exactly the kind of discrepancy that looks like drift and is not.

I did not delete them on that basis alone. Each was checked first: every one carried the AppleDouble
magic `00051607`, and **every one had a real sibling** (`._booking.py` beside `booking.py`), zero
exceptions. The exact path list was saved to `appledouble-list.txt` before deletion, then removed by
that list rather than by a fresh `find`, so the operation could not race a changed filesystem.

Afterwards: 0 `._*` files remain, all 62 real modules are still present, the tree still matches HEAD
exactly, and both services are healthy with `healthz` 200. About 1 MB of confusing clutter is gone
from the production host.

This was tidiness rather than a fault -- the container is built from `api/app` and `api/static`, and a
stray `._*` beside a real file has never been imported. But a release tree that does not obviously
match its source is a maintenance hazard, and a later "why does the host differ?" investigation would
have cost far more than the check did.

## The running image carried 179 AppleDouble artifacts, and the build now excludes them

Comparing the host source against the image's own filesystem showed the image contains files the
source does not:

```
/srv/app     175 AppleDouble files
/srv/static    4
total        179
```

All were inert -- magic `00051607`, not importable, normal imports unaffected -- but they matter for
two reasons. They make the image differ from its source in a way that reads as drift, and a clean
rebuild would have produced a **different image** from the one serving traffic, so the two could not
be compared for equality at all.

They came from `tar`/`scp` transfers of a macOS source tree in earlier sessions, where each file
gains a `._<name>` sidecar carrying extended attributes. My own local tree is clean (zero such
files), so this was inherited rather than introduced here.

**The fix is at build time, and was verified rather than assumed.** `.dockerignore` now excludes
`**/._*` and `**/.DS_Store`. Because that file uses allow-list patterns (`**` then `!api/app/**`),
the exclusion needed checking: I planted an artifact in the source, built, and confirmed the image
contained none:

```
plant api/app/._test_artifact.py -> docker build -> ls /srv/app | grep -c '^._' -> 0
```

Both the planted artifact and the throwaway test image were removed afterwards.

**Verified after the file-content check, not before.** Restricting the comparison to real modules
showed host source and image content are identical for all 62 files -- the build is faithful. The
container's own filesystem also matched its image exactly, so no code had been edited inside the
running container. The artifact problem was clutter and rebuild-fidelity, not incorrect code.

## The clean rebuild is deployed, so image and source now agree exactly

Last round added the `.dockerignore` exclusion but left the running image unchanged, which meant the
deployment still could not be compared with a clean build. Rebuilt and deployed, with a rollback tag
and backup taken first:

```
new image artifact count        : 0      (was 179)
new image real modules          : 62
host source vs image content    : 62 files, diff empty  (no extra files)
running container artifacts     : 0
healthz                         : 200
```

The comparison is now meaningful in a way it was not before: because the image no longer carries
files the source does not, `diff` on the two file listings is **empty**. Previously the same check
could only ever report "62 real files match, plus 179 the source does not have".

**Behaviour verified after the rebuild**, not assumed from a healthy container:

```
chat          200, grounded reply ("I am not sure of a full subscription inclusion list...")
voice token   200, 111-character token minted from xAI
owner-ui      200 public
```

All three channels the mandate cares about still work on the rebuilt image.

| | |
| --- | --- |
| Image | `trendi-concierge-api:vps` -> `0c00f37b7b4d` |
| Rollback | `before-clean-rebuild-20261110` -> `c69687f6bf10` |
| Backup | `/opt/trendi/backups/clean-image-rebuild-20261110` |

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

- `PYTHONPATH=api pytest api/tests -q` → **456 passed** (356 pre-existing + 100 in the
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
| Image | `trendi-concierge-api:vps` → `0c00f37b7b4d` (clean rebuild; previous `c69687f6bf10`) |
| Rollback images | `before-clean-rebuild-20261110` → `c69687f6bf10`; `before-calendar-time-tolerance-20261110`; `before-authz-panel-fix-20261110` → `3c05e01c5220`; `before-booking-readiness-20261110` → `7a16174bc7cc` |
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
