# Why Conrad's record was incomplete — and what was fixed

The question was why a real prospective customer sat in the CRM as
`conrad@pukekoconstruction.co.nz` with no name, when his own email said who he was.

## What we actually held

```
lead    email only, name '' , phone '' , channel email, 2026-11-11
case    email:conrad@pukekoconstruction.co.nz, display_name ''
```

His email, in full:

```
We specialize in the supply and installation of Nu-Wall cladding ...
Best regards,

Conrad Schiess
Pukeko Construction
conrad@pukekoconstruction.co.nz
```

**His name and company were in the message. Nothing read them.** Capture stored the envelope
address and the body, and no step ever looked at the signature. He gave **no phone number at all** in
that message, so a blank phone was correct — but a blank *name* was not.

## Three defects

**1. Signatures were never read (the direct cause).** New `app/email_signature.py` finds the closing
word ("Best regards"), takes the few lines under it, and extracts a person's name, a company and a
phone — only when each is unambiguous, because a wrong name on a customer is worse than a blank.
Wired into the email ingress, it now fills `leads.name`, `leads.company`, `customer_cases.display_name`
and `customer_cases.company`.

**2. There was no company field at all.** A B2B enquiry is half company and we had nowhere to put it.
Added `company` to `leads` and `customer_cases`, returned it from `/owner/contacts`, and shown it in
the Contacts table and the detail card.

**3. Every tenant had an empty country code, so local numbers were given a US one.** `normalize_phone`
defaulted to `"1"`. That is where `+10278817368` came from — a New Zealand mobile prefixed with a US
code, undiallable, and (worse for this module) a different case identity from the same person dialling
`+64278817368`. All four tenants now carry `default_country_code = '64'`, and an unknown country is
now honoured as unknown: `normalize_phone("021 555 1234", "")` returns `None` rather than inventing a
prefix.

## Repair of existing data

* Conrad: name `Conrad Schiess`, company `Pukeko Construction`, case display name set.
* The mangled number `+10278817368` corrected to `+64278817368` across `leads`,
  `customer_addresses` and `customer_cases.case_key`, with a `pg_dump` taken first
  (`/opt/trendi/backups/signature-backfill-20261113/before.dump`).
* **19 leads still have no name.** They are chat and phone enquiries with no email body to read — there
  was never a signature to parse. They are not a bug; they need the owner, or the AI in conversation,
  to record a name.

## Proof

* `tests/test_email_signature.py` — 5 tests, including **Conrad's real email** as the fixture.
* `tests/test_customer_addresses.py` — a named customer keeps name and company.
* `tests/test_phone_normalization.py`, `tests/test_units.py` — the US tests now state their country
  explicitly instead of relying on the removed silent default.
* **1024 tests pass** against a real Postgres.
* Live, in the Studio as the business owner: Contacts shows **"Conrad Schiess · Pukeko Construction"**,
  0 JS errors.
