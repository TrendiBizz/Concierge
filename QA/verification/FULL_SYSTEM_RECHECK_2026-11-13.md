# Full system recheck after the capture fixes (13 Nov 2026, 18:20 NZ)

The operator asked for every system rechecked and any fault fixed. Five were found, all fixed,
tested and deployed in this session.

## What was checked, and the result

| Area | Result |
|---|---|
| Containers (12 services) | all up; api healthy; no restarts beyond my own deploys |
| Disk / memory | 63G of 154G used (41%); 7G RAM, 2G used |
| Backups | daily timer ran 14h ago; restore-test timer scheduled 30 Nov |
| TLS | concierge.trendibizz.com valid to **22 Jan 2027** |
| Public routes | studio 200, owner-ui 200, trendibizz.com 200, pukekoconstruction.co.nz 200 |
| Owner screens | Contacts, Quotes, Products, Permissions, Team all load, **0 JS errors, 0 5xx** |
| CRM capture audit | 0 orphaned enquiries, 10/10 emails and 5/5 calls linked |
| Healthcheck | **39 ok, 1 warn, 0 fail** (warn = inbound SMS unproven) |
| API tests | **1040 passed** against a real Postgres |

## The five faults found — every one was live

**1. Inbound email was completely broken.** `inbound_email` called `email_signature.parse_signature`
without importing it. Every real inbound email raised NameError, and the API answered
`400 {"detail":"Invalid email payload"}` — no draft, no lead, no customer. Nothing caught it: the
tests around inbound mail exercised helpers, the healthcheck checks configuration, and my own seeding
used `enquiries.capture` directly rather than the real ingress.
*Fixed:* the import. *Guard:* `tests/test_inbound_ingest_capture.py` drives `ingest_verified` against a
real Postgres and asserts the sender becomes a customer with the signature's name, company and phone.

**2. Onboarding silently never created a reply address.** `owner_onboarding` used
`reply_address.ensure` without importing the module, inside `try/except` that logged and continued.
Every owner who saved onboarding with an email got "saved", no reply address, and no inbound email
path. *Fixed:* the import. *Guard:* `tests/test_no_undefined_names.py`.

**3. A US phone prefix was invented whenever the tenant's country was unknown.**
`casetimeline.case_key` defaulted `default_cc` to `"1"`, so a local `027 555 8801` became
`+10275558801` — the same fault as Conrad's record, in the identity layer rather than the parser.
*Fixed:* unknown stays unknown; a local number is not guessed. *Guard:* test in
`test_phone_normalization.py` asserting `case_key("027 555 8801", "")` is None.

**4. A sender with a display name was refused.** `"Marcus <m@h.co.nz>"` produced "Valid single email
address required" and a 400. The worker normally sends a bare address, but a display name must never
be the reason a customer's mail is lost. *Fixed:* `bare_address()` normalises it. *Guard:* test.

**5. Our own deploys paged the operator.** The container check treated `Up 3 seconds (health:
starting)` as a FAIL, so each deploy produced `[Concierge FAIL] container:trendi-api-1`. *Fixed:*
a container started within 10 minutes is a **warning** ("still warming"). *Proof:* restarted the api
and the check reported `container:trendi-api-1 -> Up 3 seconds (health: starting) (restarted within
10 minutes, still warming)` as a warning; after warm-up, 39 ok / 1 warn / 0 fail.

## Live proof that inbound email now captures properly

A signed POST to `/api/v1/inbound/cloudflare`, exactly as the Cloudflare worker sends it:

```
inbound response: 200 {"accepted":true,"draft_id":97}
lead:     name Marcus Whitcombe · company Harbour Joinery · phone 027 555 8801
customer: Marcus Whitcombe · Harbour Joinery · +64275558801 · marcus.whitcombe@harbourjoinery.example.nz
history:  2 events
```

Test rows were deleted afterwards (`test rows left: 0`).

## The general lesson, now enforced

Two of the five were "a module referenced something it never imported" — invisible until the exact
code path runs. `tests/test_no_undefined_names.py` now walks every module's syntax tree and fails if a
name is used without being bound, so this class cannot reach production again. It was mutation-checked
by removing the new import and watching it go red.
