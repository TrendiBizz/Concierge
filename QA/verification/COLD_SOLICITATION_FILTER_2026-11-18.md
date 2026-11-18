# Cold supplier pitch treated as customer enquiry — 2026-11-18

**Cause.** 18 Nov 15:31 NZDT a Shenzhen factory pitch from `prod@zenithen2.com` reached
`admin@trendibizz.com` (address is published on the site). It had no `List-Unsubscribe`
header and used a throwaway sender domain, so the robot filter missed it. Concierge
classified it as "Email enquiry for Trendi Concierge" and forwarded an owner alert.

**Fix.** `api/app/automated_mail.py`: `SOLICITATION_PHRASES` + `solicitation_reason()`,
wired into `classify()`. Body match => no lead, no alert, stored as discarded draft.
Phrases are narrow (e.g. "no longer wish to receive", "do you currently source",
`alibaba.com`).

**Proof.** `test_cold_supplier_pitch_is_not_an_enquiry` (also asserts a real customer
saying "please unsubscribe my old address and quote for hinges" still passes).
Mutation: fix removed -> test red; restored -> green. Full suite: 1528 passed, 19 skipped.

**Not covered.** Gmail-side filter on `zenithen2.com` is manual (connector not authorised).
