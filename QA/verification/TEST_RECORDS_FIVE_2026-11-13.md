# Five test records, created through the real capture paths

Operator asked for five records to test with. They are in `trendi-meta-review` (the review workspace),
created through the same code the live channels use — not inserted by hand — with owner alerts muted.

| # | Channel | What it proves | Result |
|---|---|---|---|
| 1 | Email | A signature names the person and the company | **Sarah Whitfield · Acme Construction**, phone +64215557001, email captured |
| 2 | Website chat | Details given in passing are read | **Dave · Kowhai Builders**, phone +64275557002 |
| 3 | Inbound call | Caller ID becomes the customer | case `phone:+64215557003`, transcript stored, no name (caller never gave one) |
| 4 | Inbound text | Sender number, the name signed on the last line, and the business named in the message | **Maria · Hutt Plumbing**, +64215557004 |
| 5 | Booking | Two-step read-back, then a real appointment | **Tom Aitken**, 20 Nov 09:00 NZDT, appointment stored, **lead linked**, **history event written** |

Verified on the real Contacts screen as the business owner: all five names present, **0 JS errors**
(`/tmp/walk10/contacts_five.png`).

## Defects the exercise found, all fixed

**1. An email signature was only read by the inbound-email handler.** Any other path that lands an
email body — a forwarded message, an import, a webhook — would store the email and lose the name and
company written right under it. Signature parsing moved into `enquiries.capture`, the shared funnel,
so no caller can miss it.

**2. A business named without "from" or "at" was dropped.** "Hutt Plumbing" in Maria's text was
ignored because the extractor only took a company after a phrase like "from Acme". A conservative
rule now accepts a capitalised name followed by a business word (Builders, Plumbing, Ltd…), and
**cannot cross a line break** — my first attempt glued "Sarah Whitfield" to "Acme Construction",
which the tests caught immediately.

**3. A booked appointment left the customer with no history.** The appointment and the customer were
both created and linked, but the customer's timeline stayed empty — a person in Contacts with an
appointment and no record of why we know them. `booking.book` now writes a `case_events` row tied to
the appointment. Every fix is mutation-checked in tests; **1036 tests pass**.

## How to remove these five when you are done

```
docker exec -i trendi-postgres-1 sh -c "psql -U \$POSTGRES_USER -d concierge" <<SQL
DELETE FROM appointments WHERE tenant_id=(SELECT id FROM tenants WHERE slug='trendi-meta-review');
DELETE FROM leads WHERE tenant_id=(SELECT id FROM tenants WHERE slug='trendi-meta-review')
  AND (phone = ANY('{+64215557001,+64275557002,+64215557003,+64215557004,+64215557005}')
       OR email IN ('sarah.whitfield@acme.example.nz','tom@aitkenjoinery.example.nz'));
DELETE FROM customer_cases WHERE tenant_id=(SELECT id FROM tenants WHERE slug='trendi-meta-review')
  AND primary_phone = ANY('{+64215557001,+64275557002,+64215557003,+64215557004,+64215557005}');
SQL
```

Nothing was sent to anybody: `notify_email` and `notify_phone` were muted on the object the code saw
as well as in the database, and restored afterwards (`alerts restored to: admin@trendibizz.com`).
