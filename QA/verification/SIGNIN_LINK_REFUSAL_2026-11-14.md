# A valid, unused sign-in link answered "expired"

Second report of the same symptom. The link was not expired, not used, and its token hashed
exactly to the stored row — so this was a defect in the exchange, not in the link.

## What actually happened

`accept_invite` refused with `Account already exists` whenever a link whose purpose was `invite`
was redeemed for an account that existed. The endpoint caught **every** `ValueError` and replied:

> This link has expired or has already been used. Ask for a new one below.

The account existed only because an operator link had already created the user (that path mints an
`invite` token when no user exists, by design). So the genuine, emailed invitation was dead the
moment the operator tested access — and the message blamed expiry, which sent two investigations
after the wrong fault.

Reproduced before fixing:

```
POST /owner/auth/invite  {"token": "<4332…>"}  →  400
row 133: token_hash = sha256(token) ✓, used_at NULL ✓, expires_at > now() ✓
```

## Fixed

1. **A valid invitation signs an existing account in.** Only a `recovery` link still requires the
   account to exist; an `invite` link no longer fails when it does. Missing the user is the normal
   case; finding one is the normal case for a second invitation.
2. **The refusal says what happened.** Unrecognised reasons are passed through instead of being
   rewritten to "expired or already used"; only genuinely stale links get that sentence.

## Proof

| Check | Before | After |
|---|---|---|
| The exact token that kept failing | **400** | **200**, `access_token` returned for support@trendibizz.com |
| Full suite | 1141 | **1145** |
| New tests | — | `test_a_valid_invitation_signs_in_an_account_that_already_exists`, `test_the_refusal_says_what_actually_happened` |

A fresh invitation (row **135**, unused, valid 24 h) was then sent to support@trendibizz.com;
outbox status **sent**, attempts 1.
