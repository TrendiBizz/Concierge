# 2026-11-27: delete scratch tenants test-1..3, tester-1..3

## Cause
healthcheck `inbound:chain` / `inbound:onboarding` kept alerting (FAIL+WARN) because six scratch tenants had no owner_account/consent. They were onboarding-test throwaways from 24-25 Nov.

## Fix
Jo approved deletion ("delete the tests, we can redo them after"). Checked first: each tenant had 0 conversations and 0 knowledge chunks. Deleted with the repo script `KEY=./Concierge ./scripts/vps/make-tester-logins.sh --delete test-1 test-2 test-3 tester-1 tester-2 tester-3` (admin API, HTTP 200 each). Remaining tenants: acme, concierge, pukeko-construction (untouched), trendibizz, trendi-fictitious, trendi-meta-review, trendi-oauth-staging, trendi-support.

## Proof
`healthcheck.py` on the box after deletion: warn 0, fail 0, no failures. To redo tests later: `make-tester-logins.sh test-1 ...` or `test_tenants.py create` (note: new tenants will trip the same check until they have owner_account/consent, so remove them after testing).
