# CRM capture re-audit: what we were missing, and what now proves we aren't

The operator asked for every capture path rechecked after Conrad's record was found incomplete. This
is that audit, run against production, plus the two defects it found and the standing check that now
prevents them recurring.

## Method

`scripts/qa/crm_capture_audit.py` — read-only, run inside the api container. For each tenant it
compares **what arrived** (leads by channel, inbound emails, calls, appointments) with **what the CRM
holds** (customer records, links, names, duplicates), and flags any enquiry that carried contact
details but never became a customer.

## What it found

**Defect: booking created a lead and no customer.** `app/booking.py` wrote `leads` with a name, email
and phone and never reconciled a customer, so anyone who booked an appointment was **absent from
Contacts** — a confirmed appointment with somebody the CRM showed nothing about. Five enquiries were
already in that state (three phone/chat, two email), created between 8 and 12 Nov.

**Not defects, and worth saying plainly:**
* an inbound email with no matching customer email turned out to be a person keyed by **phone**. The
  lead was linked correctly; my first audit query joined on `customer_cases.primary_email` and
  reported a false gap. The audit now counts linked enquiries, not matching emails.
* two `capture.email@portability.test` drafts in the review tenant were **my own** test emails from an
  earlier probe. Deleted.

## Fixed

* `booking.book` now reconciles the customer before the booking transaction and stores `case_id` on
  the lead, including when a lead already existed.
* The five orphaned enquiries were linked to their customers (`linked: 5 | still orphaned: 0`), using
  the same reconcile the live paths use, so no data was invented.
* `crm:capture` added to the healthcheck: it **fails** if any lead has contact details but no customer.
  Healthcheck went 37 → **38 ok**, one warn (`sms:inbound`), one fail (`inbound:chain`, known).

## Proof, after the fix

```
pukeko-construction      emails 2/2 linked     calls 0/0     orphans 0
trendi-oauth-staging     emails 10/10 linked   calls 5/5     orphans 0
customers named:         pukeko 1 of 3         oauth 0 of 10 (test records)
duplicate customers:     0
customers with no history: 0
```

`tests/test_booking_creates_customer.py` asserts the booking creates the customer and links the lead;
it fails if the reconcile is removed (mutation-checked). **1033 tests pass** against a real Postgres.

## Still honestly incomplete

* **Customer names are mostly empty** — `pukeko` 1 of 3, `oauth` 0 of 10. For email we now read
  signatures; for chat and phone a name exists only if the person says it. Test records will stay
  nameless.
* **Appointments: 0 in production**, so the booking capture fix is proven by test, not by a live
  booking. The first real booking will be the live proof.
* **Inbound SMS** remains unproven (see the SMS live proof record).
