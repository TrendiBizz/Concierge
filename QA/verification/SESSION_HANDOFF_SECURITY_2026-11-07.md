# Trendi Concierge — continuation after owner security hardening (2026-11-07)

## Verified worktree
- Mac: Mac.hub
- Worktree: /Users/jo/work-staging/concierge-integration
- Branch: integration/concierge-v1
- Current local-only commit: bb832d9 Harden tenant owner endpoints and shared login throttling
- Prior commits: 3997843 owner UI, b2025c1 owner RBAC, f7dee40 guarded email/phone.
- Never touch /Users/jo/concierge (live-adjacent original checkout).
- Preserve untracked QA/verification/office-shots/; do not commit.
- No push, merge, deploy, phone or email enablement, paid-provider account changes, or production modifications without separate approval.

## Completed in this continuation
- Read both handoffs and confirmed branch state.
- Replaced process-local owner login limiter with atomic PostgreSQL counters scoped by hashed IP and hashed (IP,tenant,email); 8 attempts per rolling 5-minute fixed window.
- Added owner-only same-origin rejection of foreign Origin headers, including OPTIONS preflights; no-store, nosniff and no-referrer responses.
- Added owner_login_limits table/index in additive schema.
- Added QA/verification/owner_security_integration.py with 12 boundary/regression checks.
- Verified unit 52/52, owner RBAC 30/30, new owner security 12/12 PASS on disposable pgvector PostgreSQL.
- Docker test DB removed; original running containers untouched.
- Local git commit bb832d9. Existing office-shots remain untracked.
- The temporary RBAC runner's first shell reported rc=1 solely because zsh reserves variable name 'status', AFTER 30/30 checks passed. Its disposable container was removed manually. Do not use variable 'status' in zsh shell wrappers; use 'result'.

## Open risks / next steps (strict priority)
2. Owner security is improved but not certified: ensure server reverse-proxy origin behavior, lockout cleanup and monitoring, session cleanup, role-change revocation, token distribution risk and a full independent review. Rerun owner portal Chrome checks using disposable DB.
3. Provider NOT selected by user: need explicit choice (Mailgun or Brevo or other), inbound destination subdomain and sender identity rules before implementing a PUBLIC inbound webhook.
   - Mailgun documents signed inbound routes using timestamp/token/HMAC-SHA256 and a webhook signing key.
   - Brevo supports inbound parsing and configurable authentication; validate its exact selected webhook auth mode before implementing.
   - Do not equate provider-independent ingest_verified with authenticated webhook.
   - No live inbound ingestion endpoint exists; outbound approvals remain gated/disabled.
4. Actual Twilio number ownership, telephony transfer/interruption and NZ PSTN tests require separate user approval.
5. Product, CSP, marketing copy, privacy/legal approvals pending.
6. CI, lock/secret scan, backup restore, monitoring, retention/deletion and rollback proof pending.
7. Staging and production remain UNAUTHORIZED.

## Safe tests
cd /Users/jo/work-staging/concierge-integration
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
For owner DB checks, start a UNIQUE disposable pgvector/pgvector:pg16 container on 127.0.0.1:55432, run owner_rbac_integration.py and owner_security_integration.py in SEPARATE FRESH databases (seed tenant names collide otherwise), and delete only the test container after each suite. Both set OUTBOX_ENABLED=false.
