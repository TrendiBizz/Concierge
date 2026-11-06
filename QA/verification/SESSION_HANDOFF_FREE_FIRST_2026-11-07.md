# Trendi Concierge — free-first continuation checkpoint (2026-11-07)

## Where to resume
- Device: Mac.hub.
- Isolated worktree: /Users/jo/work-staging/concierge-integration.
- Branch: integration/concierge-v1.
- New implementation commit: fcc784f (Cloudflare email bridge + tests + CI + restore proof).
- Prior commits: c579cc1 (previous handoff); bb832d9 (owner security); 3997843 (owner UI); b2025c1 (RBAC).
- Inspect git log -2 to see this handoff's commit.
- Keep original /Users/jo/concierge and live Docker containers untouched.
- Preserve QA/verification/office-shots/ (untracked before continuation).
- NEVER push, merge, deploy, activate email/phone, change MX/DNS, provision paid service, or edit production without separate approval.

## Free/open-source evaluation
See QA/verification/OPEN_SOURCE_DECISIONS_2026-11-07.md.
Preferred inbound free-first path: Cloudflare Email Routing (domain must be on
Cloudflare DNS; inbox MX changes require owner approval) + free Workers tier +
postalsys/postal-mime MIT-0. Worker/API HMAC bridge completed locally, not deployed.
Voice alternatives Pipecat and LiveKit were researched; avoid replacing the
existing Twilio adapter before tests with real NZ PSTN.
Existing Uptime Kuma is present: use it rather than installing another suite.
Trivy CI scan staged, restic suggested for encrypted offsite copies (not installed).
GitHub Actions billing/quota must be checked before running remote CI.

## Code delivered
- api/app/cloudflare_inbound.py: bounded HMAC/timestamp signed ingress, private
  enabled mailbox-to-tenant mapping, dedup via inbound_email, no AI/send.
- integrations/cloudflare-email/: Cloudflare Email Worker + postal-mime, locked
  dependencies, inactive wrangler config, setup/limitations instructions.
- Admin-only POST /admin/tenants/{slug}/inbound-mailboxes, defaults disabled.
- POST /api/v1/inbound/cloudflare exists in code but feature is disabled
  by default and not deployed; API requires INBOUND_CLOUDFLARE_ENABLED=true and
  32+ char signing key. No public webhook enabled.
- QA/verification/cloudflare_inbound_integration.py: signed injection and
  ownership/regression checks.
- .github/workflows/concierge-isolated.yml: 11 independent Python suites,
  Trivy and syntax static checks, disposable pg_dump restore proof.
  Draft workflow was NOT run on GitHub and has no reported green CI result.
- QA/verification/restore_disposable.sh passed isolated Docker canary restore.
- Product/site reconciliation in OPEN_SOURCE_DECISIONS: PRODUCT.proposed.md is
  UNAPPROVED. Code has rule-based lead scoring, NOT model/AI lead scoring.

## Verified local results
- Python units 52/52 PASS.
- Existing owner RBAC 30/30 PASS (earlier in same session).
- Owner security 12/12 PASS.
- Cloudflare HMAC ingress 16/16 PASS.
- Owner portal live Chrome 7/7 PASS.
- Fresh DB integration: email drafts 25/25, simulated phone 22/22, scoring
  12/12, phase3 21/21, campaigns 24/24, campaign routes 19/19, office
  63/63: total 186/186 PASS.
- Aggregate 303 checks across the above suites (not an E2E certification).
- Disposable restore PASS, JS syntax PASS, Python compileall PASS, git diff
  check PASS.
- No paid-provider calls, SMTP sends, real calls, public workers, DNS updates,
  persistent DB changes or production deployment.

## Work remaining in original order
2. Owner security: independent review, proxy policy, lockout cleanup and
   monitoring, session lifecycle cleanup, additional audit/operational logging.
3. Cloudflare email: explicit account/DNS/MAILBOX approvals, credentials
   installed privately, test Worker in live environment, DMARC/SPF and sender
   identity policy, retry/drop behavior, end-to-end inbound test. No SMTP sends.
4. Telephone: TWILIO number ownership, paid-account approval, NZ inbound call,
   interruption/hangup, transfer-to-human, privacy notice/consent tests.
5. Product: explicitly approve revised PRODUCT.md and site CSP; edit DESIGN.md
   and Privacy/Terms with legal review. No public claims for local-only features.
6. CI/workflow: remote GitHub CI run only after authorized push; dependency audit,
   verified offsite encrypted backups, production restore rehearsal, monitoring
   alert routing, agreed retention/deletion, spend cap and rollback rehearsal.
7. Staging then production need separate explicit authorizations, never inferred.

## Important caveat
Free source code is not the same as no-cost operations. Cloudflare DNS/MX and
account restrictions, telephony/carrier, model inference, paid SMTP and GitHub
private-runner minutes must be verified against account entitlements.

## Next commands, Mac zsh
cd /Users/jo/work-staging/concierge-integration
git status --short --branch
git log -3 --oneline
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
bash QA/verification/restore_disposable.sh

Use fresh disposable pgvector databases per integration suite (all bound to
127.0.0.1:55432). Do not combine seeded suites without resetting DB.
