# Owner-alert emails must not show internal ids or dedupe keys (2026-11-26)

## Cause
The explainer video showed a "Dedupe key" line on the owner-alert card (fixed in v8). Jo asked whether the
real product email does the same. Code read: subject, body and headers never include `outbox.dedupe_key`
(`enquiry_alerts.render/subject_for`, `outbox.py` email branch). One stray internal line did exist: the
website-enquiry operator email ended `Reply to <email>. Enquiry <id>; also visible in Studio CRM.`

## Fix
- `api/app/site_enquiry.py`: line is now `Reply to <email>; also visible in Studio CRM.` (no row id).
- `api/tests/test_site_enquiry.py`: two regression tests.
  - operator email: no dedupe/internal words, no dedupe key, no row id, and every body line must match an allowed prefix (no stray lines).
  - owner enquiry alert (`enquiry_alerts.render` and `subject_for`, all channels): no dedupe/internal words, no tenant-key fragment.

## Proof
- Mutation A (restore `Enquiry {enquiry_id}` line): operator-email test fails. Restored.
- Mutation B (add `Dedupe key: enq:x` line to `enquiry_alerts.render`): owner-alert test fails. Restored.
- Full suite: 1928 passed, 42 skipped.
- Not verified: a delivered real email (never replayed to production).
