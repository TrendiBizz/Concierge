# Owner link grace expiry + empty-account launch refusal (2026-11-25)

Live, via https://concierge.trendibizz.com, scratch tenant `scratch-1` (made with `make-tester-logins.sh`, deleted afterwards). Browser User-Agent used (default urllib UA gets edge 403 1010).

| step | time (UTC) | result |
|---|---|---|
| redeem link `POST /owner/auth/invite` | 01:35:23 | 200, owner session |
| same link again, seconds later (inside 30 min grace) | 01:35 | 200 (by design, `GRACE_MINUTES = 30`) |
| `PUT /owner/onboarding/progress {"launched":true}` on empty tenant | 01:36 | 409 "Before you launch, add: business name and website, knowledge (read your website or add a note), an alert email." |
| same link again, 30 min 39 s after first use | 02:06:02 | 400 "This link has already been used. Ask for a new one below." |

Cause/fix: none, no defect. Both refusals behave as designed (`owner_auth.accept_invite`, `owner_portal` launch gate).
Cleanup: `make-tester-logins.sh --delete scratch-1` run after the test.
No mail, SMS or calls sent.
