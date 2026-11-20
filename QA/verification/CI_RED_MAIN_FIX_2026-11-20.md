# CI red on `main`: cause, fix, proof (20 November 2026)

`main` at 054954d failed three jobs of "Concierge isolated verification": `socialsync-node`,
`isolated-phone_relay_integration`, `isolated-cloudflare_inbound_integration`. Each was reproduced locally
(Postgres 16 + pgvector, Python 3.13, Node 22) before any change.

## 1. `isolated-cloudflare_inbound_integration`: a real defect

- **Symptom:** "oversized event rejected" expected 413, got a success.
- **Cause:** `cloudflare_inbound.handle()` runs `inbound_text.clean_inbound_text()` before its
  `len(text) > 20000 -> 413` check. The cleaner truncates its output to 20,000 characters, so the check could
  never fire: an oversized body was silently cut and accepted.
- **Fix:** `api/app/cloudflare_inbound.py` asks the cleaner for `limit=20001`. A body still over 20,000 characters
  after HTML/stylesheet cleaning is now a 413 again; HTML mail that is large only because of stylesheet text is
  still cleaned and accepted.
- **Tests:** the existing integration check now passes; added "stylesheet-heavy HTML mail is cleaned, then
  accepted" (raw over 20,000 characters, cleaned well under) so the fix cannot over-reject real mail. The source
  pin in `api/tests/test_inbound_text_cleaning.py` was updated to the new call.
- **Mutation:** before the fix the oversized check failed (that was the red CI).

## 2. `isolated-phone_relay_integration`: the test was stale

- **Symptom:** "operator can opt in one business" got HTTP 409 `alerts_not_proven`.
- **Cause:** `PATCH /admin/tenants/{slug}` has a go-live gate: phone cannot be switched on until owner alerts are
  proven (mobile, email, a delivered test alert) unless the operator passes `?force=true`. The test predated it.
- **Fix:** test only; product code unchanged. The suite now asserts the refusal (409, `alerts_not_proven`, at least
  one blocker), asserts the business stays off, then opts in with `?force=true`.
- **Mutation:** with the gate disabled in `main.py` (`if False and blockers`), the new refusal check failed.
  Restored, confirmed `git status` clean for `main.py`.

## 3. `socialsync-node`: the tests were stale (three failures)

- **Symptom:** `owner_customer_journey_test.cjs` tests 2, 6 and 7 failed.
- **Cause:** two deliberate product changes. (a) An invitation link now signs the owner in directly through
  `POST /owner/auth/invite` instead of filling `redeem-token`. (b) The portal calls `/version` on every load, so
  "zero requests" can never hold.
- **Fix:** tests only; `api/static/owner.html` unchanged. The test harness now records the address-bar state at
  each request. Tests now prove the guarantees that still matter: the `#invite=` fragment is removed before the
  first request leaves, the token is never left in a form field, a malformed fragment is never sent, an expired
  link returns to sign-in with guidance, and mismatched recovery passwords make no request and keep the token.
- **Mutation:** removing the `history.replaceState` call failed two tests; removing the password-mismatch guard
  failed one. `owner.html` restored, `git status` clean.

## Proof (local, same commands as CI)

- All 15 integration suites in the CI matrix pass.
- `node --test` in `concierge-stack/socialsync`: 19 pass, 0 fail. The three widget/journey/operator files: 11 pass.
- Unit suite (`pytest api/tests -m "not hangs_on_py312"`): 1543 passed. Two `test_studio_deploy_window.py` tests that
  `chmod 000` a file fail only when run as root (root ignores permissions); as a non-root user all 5 in the file pass.
- `python3 -m compileall -q api/app QA/verification` and `git diff --check`: clean.
- Not run locally: the Trivy scan (it passes on `main` in CI). `node --test` at the repo root also has 6 failures
  that need `puppeteer-core` (a real browser); CI does not run them.
