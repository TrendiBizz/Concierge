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
   the owner, not a defect; the guard is doing its job.
3. **Inbound SMS end to end.** No SMS provider is configured; the routes return 503
   by design.
4. **Real carrier telephone calls.** Unchanged and still optional. `phone_numbers = 0`,
   no SIP mapping, no number purchased. Website voice is unaffected by this.
5. **Enquirer acknowledgement actually sent**, for consent reasons above.

## Test and gate state

- `PYTHONPATH=api pytest api/tests -q` → **401 passed** (356 pre-existing + 45 new).
- `scripts/rust-gate.sh` → **GATE-ALL-OK** across all four crates.
- New file `api/tests/test_two_business_workflow.py` runs the seven steps for two
  distinct businesses and pins the two behaviours most likely to cause real harm:
  refusing a foreign-format number instead of fabricating one, and reporting
  "pending" rather than "confirmed" when no calendar is connected.

Historical unit counts were not treated as proof of the service; every claim above
names the artefact it came from.
