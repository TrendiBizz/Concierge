# Tester logins tester-1..3 (2026-11-25)

Ask (Jo): three numbered test logins for three outside testers; one full run by us first.

## What was made
- `scripts/vps/make-tester-logins.sh slug...` creates an empty tenant if missing and mints one
  single-use owner link via admin API `POST /admin/tenants/{slug}/owner-invitations`
  (`send_email=false`, no mail goes out). `--delete` removes scratch tenants.
- Tenants `tester-1`, `tester-2`, `tester-3`: verified on box empty (0 chunks, no notify_email, not launched).
- Link facts (code): single use, 24 h expiry, 30 min grace for a double-fired redeem (`accept_invite`).
  Placeholder owner address is `<slug>@trendibizz.com`; a tester cannot request their own
  email link (`/owner/auth/link` mails that placeholder) -> operator mints a new link on request.
  Session lasts 30 days (`expires_in` 2592000).

## Own run on scratch tenant `tester-scratch` (deleted afterwards), via public https://concierge.trendibizz.com
| step | result |
|---|---|
| redeem link `POST /owner/auth/invite` | 200, owner session |
| same link again within grace | 200 (30 min grace, by design) |
| `GET /owner/me`, `/owner/onboarding` | 200 |
| test-alert with no notify email | 422 "Add a valid notification email address first." |
| profile PATCH name/site/notify_email | 200 |
| import website | 200, 15 pages, 121 chunks |
| test-chat (dry run) | 200, correct pricing answer, no lead created |
| preview-slots | 200, real slots |
| test-alert | 200 queued to `tester-scratch@trendibizz.com` only |
| launch `PUT /owner/onboarding/progress {launched:true}` | 200, `launched_at` set |
| logout then `/owner/me` | 401 |
Not fully exercised in this run: launch refusal on an empty account (my first launch attempts used PATCH -> 405,
so the 409 gate was NOT observed live; it is covered by the existing onboarding gate tests/audit
`QA/verification` onboarding launch gate). No real SMS or calls.

## Trap found
Python urllib default user agent gets edge 403 "error code: 1010"; send a normal browser UA in scripted checks.
