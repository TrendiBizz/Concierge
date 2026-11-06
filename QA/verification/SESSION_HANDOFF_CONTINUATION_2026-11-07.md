# Concierge integration — continuation checkpoint (2026-11-07)

## Repository
- Mac: `Mac.hub`
- Worktree: `/Users/jo/work-staging/concierge-integration`
- Branch: `integration/concierge-v1`
- Previous committed base: `f7dee409acffc2a79982b57fe2a1f379e4827013`
- New local implementation commit: see `git log -1 --oneline` after saving this file.
- Do not touch live-adjacent `/Users/jo/concierge`.
- Do not push, merge, deploy, enable messaging or make paid-provider changes without the user's separate approval.
- `QA/verification/office-shots/` was untracked before this continuation; preserve, do not commit.

## Sequence status (handoff's strict order)
1. **DONE**: prior integration features were committed locally as `f7dee40`; no changes to tracked files at start.
2. **CORE API BUILT, NOT RELEASE-READY**: new tenant-owned accounts in `api/app/owner_auth.py`, schema tables for users/invitations/sessions, `/owner/*` routes and operator-driven invitation/recovery, 12-hour opaque bearer sessions, PBKDF2 password storage, owner/editor/viewer roles, read-only tenant phone resources and role-gated email draft actions. No customer-owner web login UI or complete security review yet. Existing admin UI retains global operator token and MUST NOT be presented as a tenant-owner portal. Login throttling is in-memory and must become durable/rate-limited at proxy or shared-store level before public release.
3. **SAFE CORE ONLY; PROVIDER BLOCKED**: `api/app/inbound_email.py` provides `ingest_verified` for a future authenticated adapter, with stable event deduplication, sender formatting and no AI/sending on receipt. It is NOT exposed as a webhook and deliberately does NOT implement Brevo/Mailgun/Postmark/SES native signature checks. Need explicit provider selection, private recipient-to-tenant binding and verified sender identity rules before implementing real ingress. Never treat the method name as provider verification. Inbound emails use a `REVIEW REQUIRED` placeholder; approval now rejects this placeholder.
4. **PENDING**: Twilio number verification/provisioning, transfer/hangup/interruption, privacy notice/consent, NZ real inbound trials. Provider/account/pricing and real call need approval. All phone settings remain off.
5. **PENDING**: reconcile product spec and site draft, obtain PRODUCT.md, CSP and legal approvals before any release.
6. **PENDING**: full isolated CI, lock and secret scan, backups restore, monitoring, tenant retention/deletion, spend cap, rollback proof.
7. **BLOCKED ON EXPLICIT APPROVAL**: stage deploy and real end-to-end pilot; production approval separate.

## Tests actually run
- Original Python units: **52/52 PASS**.
- Email PostgreSQL integration on *its own disposable pgvector container*: **25/25 PASS**.
- Simulated Twilio integration on *its own disposable pgvector container*: **22/22 PASS**.
- Owner RBAC integration after additions, disposable pgvector: **30/30 PASS**, including role/tenant boundaries, recovery session revocation and prompt-injection-as-untrusted-content check.
- Original office dashboard tests were NOT rerun in this continuation; earlier handoff reported 32/32 Chrome.
- Temporary containers were deleted after each suite. The first attempted combined run collided on seeded tenant slug; corrected by fresh DB per suite and strict exit codes. That combined run must not be counted as a pass.

## Important limitations / audit
- Provider adapter not chosen, therefore no inbound email webhook is production-ready.
- Global admin-token routes remain separate; keep this restricted to internal operator only.
- Owner approvals can enqueue email if existing `EMAIL_DRAFTS_ENABLED`, SMTP and outbox are all explicitly enabled. They remain disabled in staging tests. Do not enable.
- No paid Twilio/SMTP/xAI calls were made.
- No production services, persistent databases, main branches, or original checkout were changed.
- There has been no stage or production deployment.
- A real security review should include CSRF/CORS review, password/login anti-abuse, audit events, session expiry cleanup, token delivery, and owner UI.
- The provider-independent ingestion function is a trusted-code entrypoint only, NOT a safe public webhook. Never call it from an unauthenticated HTTP handler.

## Safe continuation
1. Read this checkpoint and `SESSION_HANDOFF_2026-11-07.md`; verify clean branch and SHA.
2. Finish owner portal/API security tests and login hardening with isolated DB; no operator-token exposure.
3. Confirm provider selection with user before wiring a native signed inbound email webhook; no live email sending.
4. Continue steps 4–7 only subject to the gates above.
5. Rerun all relevant suites in separate disposable DBs and save another local-only checkpoint.

## Commands for safe isolated unit checks
```zsh
cd /Users/jo/work-staging/concierge-integration
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
```
