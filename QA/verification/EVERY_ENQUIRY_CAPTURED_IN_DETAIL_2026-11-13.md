# Every enquiry, captured in as much detail as the customer gives

The instruction was blunt: chat, SMS or any enquiry **must** be captured in as much detail as
possible. Before this, each channel captured only the machine-readable identifier it arrived with —
an email chose from the envelope, a call from the caller ID — and everything the person *wrote*
about themselves was left in the message body for a human to re-type.

## One extractor, every channel

`app/identity.py` reads what people actually write:

| they write | captured |
|---|---|
| "hi it's Sarah from Acme Construction, call me on 021 555 1234" | name Sarah, company Acme Construction, phone +64215551234 |
| "My name is Conrad Schiess, email conrad@pukekoconstruction.co.nz" | name, email |
| "Can you come out next week?\nSarah" | name Sarah (people sign texts) |
| "We have a two-storey house with old cladding" | nothing — no invented details |

It is wired into **`enquiries.capture`**, which every channel goes through — website chat, SMS,
inbound email, social, and the voice capture paths — so a detail given on any channel is recorded
identically. Channel-supplied values always win; extraction only fills what is missing.

Deliberately conservative, because a wrong name on a customer is worse than a blank one:
* the trigger words ("my name is", "I'm", "this is") match in any case, but the captured word must
  actually look like a name;
* "I'm interested" is not a person called Interested;
* phone numbers are **not** taken from a long email thread — someone else's number further down a
  quoted reply would otherwise be attached to the wrong customer.

## The assistant may now record a name alone

`capture_lead` used to refuse unless it had a phone or email. A named enquirer with no contact
details was thrown away — the single most useful thing an owner can have when following up. It now
accepts a name, and reads the visitor's own words when the model passes thin arguments. The prompt
tells the assistant to record details **as they are given**, and again when more arrive.

## Company is captured end to end

Named company now flows: extracted → `leads.company` → `customer_cases.company` → `/owner/contacts`
→ the Contacts table and detail card.

## Proof

* `tests/test_email_signature.py` — 9 tests, including the extractor against real phrasing and the
  negative case that must produce nothing.
* `tests/test_enquiry_detail_capture.py` — 4 tests: a chat message is mined for all three details; a
  channel-supplied value is never overwritten; a name-only enquirer is saved; the company reaches
  the customer record. Each mutation-checked (removing the extraction, or the company hand-off,
  turns them red).
* **1031 tests pass** against a real Postgres.
* Live, against production, with a chat message stating name, company and number:

```
captured: {'name': 'Sarah', 'company': 'Acme Construction', 'phone': '+64215557788',
           'case_key': 'phone:+64215557788', 'display_name': 'Sarah'}
```

Test rows deleted afterwards; the review workspace is empty again.

## What is still not captured

* **Postal/physical address**: no channel collects it, and there is no field for it. Worth adding if
  the business needs it for quotes.
* **Inbound SMS**: the extractor applies, and outbound texting works (see below), but no text has
  ever been delivered *into* the platform, so this is untested end to end.
* **Careful with "SMS" as a word.** Sending and receiving are different directions with different
  plumbing. The platform **sends** texts successfully; it has never **received** one.
* **A name never stated**: the extractor cannot invent one. The assistant is now instructed to ask
  for a name when it is relevant, which is the only honest way to get it.

## A note on how this was verified

Two verification runs each emailed the operator a "[WARM] New lead" alert. Owner alerts are exempt
from a paused tenant by design, and my harness muted the database row while still handing the tool a
tenant dict read before the change. `scripts/qa/capture_check.py` is the corrected, reusable version:
it mutes the object the tool receives, restores it in a `finally`, and cleans up its own rows. Run it
from the api container — it prints PASS or FAIL and sends nothing.

## Correction: texts are working — I tested the wrong door

I previously wrote that SMS "cannot be exercised — not configured". That was wrong, and the operator
was right to push back.

**What is actually true:**

* `SMS_PROVIDER=none` has been the value in **every** `api.env` copy on disk since at least 9 Nov —
  checked across ten backups. Nothing changed it, and it is not a regression.
* Texts are sent through the **paired-phone (device) transport**, which ignores that global setting.
  `trendi-oauth-staging` has `sms_enabled=t`, `sms_transport=device`, `sms_from=+64278817368`, and
  **47 owner-alert texts were sent today**, with the phone polling as recently as 04:32 UTC.
* My capture check posted to `/api/v1/sms/{key}`, which is the **Twilio** webhook. That route
  legitimately returns 503 when `sms_provider` is not `twilio`. The 503 was correct behaviour for a
  transport the platform does not use; I reported it as though SMS itself were unconfigured.

**The real SMS gap is inbound, and it is now visible.** `sms_devices.inbound_verified_at` is `null`:
the paired phone has never delivered a single inbound text — `device_sms_inbound` has 0 rows and no
`channel='sms'` conversation exists. Outbound working proves nothing about inbound, because the phone
polls our queue either way. A customer replying to a text would currently be talking to nobody, and
nothing said so.

Two things are now true that were not before:

1. `scripts/vps/healthcheck.py` gained a `sms:inbound` check. It fails while a paired phone has never
   delivered a text in, and its message says what to do. It reports today:
   `1 of 1 paired phone(s) have never delivered a text in; send one text to the business number to
   prove the reply path`.
2. The inbound code path itself is sound and covered: `tests/test_device_sms_inbound.py`,
   `tests/test_inbound_sms_route.py` and the receipt tests pass (49 SMS/device tests green), and
   `_sms_reply` captures the sender, reconciles the customer and runs the normal consent/STOP path.

**What is still needed, and only the operator can do it:** send one text to `+64278817368` and watch
`sms:inbound` turn green. That single message proves the reply path end to end.

## Sending versus receiving — why "it worked a few days ago" is right

The operator remembered a text arriving a few days ago, and that memory is correct. It was an
**outbound** text, and it is already recorded in this repo:

* **8 Nov** — `QA/verification/LIVE_RELEASE_2026-11-08.md`: "The separate legacy Mac/iPhone provider
  is not an integrated inbound SMS adapter. No SMS was sent and no handset delivery is claimed."
* **9 Nov** — `QA/verification/HANDOFF_CONCIERGE_VERIFIED_2026-11-09.md`: "One reconciled SMS-only
  retry reached SENT with a verified Messages receipt; user confirmed exact full message
  sent/received at 14:08." That is the platform **sending** a text which then arrived on a handset.
* **9 Nov** — `QA/verification/HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md`: "Live device inbound
  verification absent. No seamless two-way claim yet."

So the position has not changed between 9 Nov and today: sending works and is proven; receiving has
never been proven. Nothing regressed in the last few days — this was already the documented state,
and the 47 texts sent today are the same working path as the one confirmed at 14:08 on 9 Nov.

My earlier wording, "SMS cannot run in this environment at all", was wrong: it is one direction that
is missing, not the capability. Corrected above.
