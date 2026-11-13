# Onboarding rechecked end to end: is it seamless?

The operator asked whether onboarding had been rechecked and whether it is seamless. It had not been,
and it was not. Four faults, all found by walking a real new client through it, all fixed and deployed.

## The walk I ran

1. Operator creates a client (`POST /admin/tenants`) → tenant, reply address, public key created.
2. Operator asks for the owner's link → **fault 1**.
3. Owner opens the link in a browser → signs in with no password, link spent, address bar cleaned.
4. Owner lands in Studio → **faults 3 and 4**.
5. Owner reads the setup wizard, checks their website, saves the business → **fault 2**.
6. Operator view of readiness before and after.

## Fault 1 — a brand-new client could not be given to its owner

`owner-recovery` answered `{"detail":"Active user not found"}`. Recovery deliberately refuses to
invent a user, which is correct for "I forgot my password" and wrong for the operator's first step:
the client exists and nobody can get in. Onboarding could not begin at all.

**Fix.** `owner_auth.owner_link()`: if an active user exists, mint a recovery link that keeps their
role; if not, mint a first-owner **invite** as owner. `POST /admin/tenants/{slug}/owner-recovery`
returns `purpose` and `role` so the operator can see which they got.

**Proof.** Live: `purpose: invite | role: owner` and a working link. Test
`test_a_new_client_gets_a_working_owner_invite` also asserts an existing viewer is *not* promoted.

## Fault 2 — every new client was placed in a US timezone

`tenants.timezone` defaulted to `America/Chicago`. A New Zealand business created without an
explicit timezone had every booking, reminder and business-hours calculation in US Central time —
and the owner would only discover it in setup, if at all. The live payload showed
`"timezone": "America/Chicago"` against a brand-new tenant while all five real tenants were
`Pacific/Auckland` (set by hand).

**Fix.** Schema default and column default are `Pacific/Auckland`; a new client is a New Zealand
business until told otherwise.

**Proof.** `select column_default …` → `'Pacific/Auckland'::text`; test
`test_a_new_client_is_not_put_in_a_us_timezone`.

## Fault 3 — a new owner landed on an empty dashboard, not setup

The redeem flow sets `sessionStorage.startAtSetup = '1'`, and the tab state reads it in a
`useState` initialiser. That initialiser had already run: the flag was set *after* mount, so it was
never consumed (measured: flag still `'1'`, Home selected, "Your business at a glance" on screen).

**Fix.** An effect watches the token and, if the flag is set, opens Setup and clears it.

**Proof.** A fresh invite now lands on `Set up Onboarding Test Co` → "How Concierge works" → the
three-step wizard, with the flag consumed.

## Fault 4 — "Pause everything" sat above the setup wizard

A first-time owner was offered "Pause now" over the wizard for a service that had never run. The
pause strip is now hidden on the Setup tab.

**Proof.** Same walk: `pause card present? False`, step 2 shows the website field and
"Check my website", no JS errors, no 5xx.

## What a new owner now experiences

```
invite link → signed in, no password → "Set up <Business>" wizard
  step 1 Welcome            → what Concierge does, Continue
  step 2 Your business      → website → Check my website → confirm name/logo/accent/timezone
  step 3 Finish             → install snippet, permissions, booking
```

Readiness for a brand-new client before the owner acts is
`owner_account: False, consent: False` and nothing else — i.e. the product correctly says what is
still missing rather than failing silently.

Tests: **1044 passed**. The test client was deleted afterwards (`test client rows left: 0`).
