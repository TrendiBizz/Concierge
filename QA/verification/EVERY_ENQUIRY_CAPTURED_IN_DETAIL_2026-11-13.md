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
* **Inbound SMS**: the extractor applies, but SMS cannot run in this environment at all — no
  provider is configured (see the open item).
* **A name never stated**: the extractor cannot invent one. The assistant is now instructed to ask
  for a name when it is relevant, which is the only honest way to get it.

## A note on how this was verified

Two verification runs each emailed the operator a "[WARM] New lead" alert. Owner alerts are exempt
from a paused tenant by design, and my harness muted the database row while still handing the tool a
tenant dict read before the change. `scripts/qa/capture_check.py` is the corrected, reusable version:
it mutes the object the tool receives, restores it in a `finally`, and cleans up its own rows. Run it
from the api container — it prints PASS or FAIL and sends nothing.
