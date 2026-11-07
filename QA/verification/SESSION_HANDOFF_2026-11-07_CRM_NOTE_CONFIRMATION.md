# Trendi Concierge continuation — 2026-11-07, CRM confirmation safety

## Starting point and required handoffs
Read both:
- `/Users/jo/work-staging/trendi-site/concierge-stack/HANDOFF.md`
- `/Users/jo/work-staging/concierge-integration/QA/verification/SESSION_HANDOFF_2026-11-07_SOCIAL_CRM.md`

On Mac.hub:
- `/Users/jo/work-staging/trendi-site`, branch `concierge-stack`, HEAD `71d0715` confirmed.
- `/Users/jo/work-staging/concierge-integration`, branch `integration/concierge-v1`, HEAD at start `6ede4d9` confirmed.
- Before this continuation only unrelated untracked `QA/verification/office-shots/` existed. Leave it untouched.

## This continuation (LOCAL ONLY; NOT pushed, merged, deployed or enabled)
- Reviewed staged private Twenty bridge design and event worker.
- Corrected `api/app/events.py`: HTTP 200 and a person id alone do NOT prove a complete CRM delivery. A `note: true` confirmation is also required; otherwise delivery becomes `uncertain`, requiring reconciliation rather than automatic retry.
- Updated the positive-path mocked response and added a regression test proving that a created person with an unconfirmed note is not marked sent.
- Existing real CRM bridge remained untouched, responding on `127.0.0.1:4410/health` with `ok: true, configured: true`.
- The optional private Docker bridge is still NOT started and CRM worker tenant settings are still not enabled by this work.
- No Rust social posting flag, production OAuth, social account, customer approval flow or live messaging enabled.
- No LiveKit/Grok voice source or running process modified.

## Verification completed
- Platform unit tests: 52 passed.
- New CRM/owner Python tests: 13 passed (previously 12).
- Node bridge tests: 19 passed.
- Existing voice suite: 54 passed.
- Rust social service: `cargo test --locked`, `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`: all passed.
- Compose overlay syntax: `docker compose -f docker-compose.yml -f docker-compose.twenty-bridge.yml --env-file /Users/jo/concierge/.env config --quiet` passed.
- `git diff --check` passed.
- Docker containers still running: Concierge API, postgres, Twenty server/worker/db/redis, Caddy, n8n, Uptime Kuma, Redis, Hermes. No restarts.

## Dependency order remaining
1. **Private transport activation** requires separate operator authorization. Read `QA/verification/PRIVATE_BRIDGE_INTEGRATION.md`. Keep the existing 127.0.0.1 bridge; NEVER publish it to 0.0.0.0. Confirm Docker network membership and secrets before configuring staged worker.
2. **CRM event idempotency**: bridge currently searches by email; phone-only duplicates and notes after ambiguous failures still require manual reconciliation. Add CRM-side event-id dedupe before claiming exactly-once behavior.
3. **Disposable end-to-end staging validation**, after approval: API -> authenticated internal bridge -> real Twenty; one lead + booking, verify note and database result; delete test data; rollback the overlay only. Do not touch current running services without approval.
4. **Social customer linking**: official OAuth, tenant consent, scoped credentials, verified customer reply approvals and revocation; Rust independent official API integration, no Postiz translation. Publisher off.
5. **LiveKit**: keep proven Grok calling; new customer-specific routing, permission-gated inbox access, consensual recording/retention and CRM booking callback during a real call remain unverified; no live calls without approval.
6. **Website/SEO, paid-provider/billing/legal and production release gates** remain separate, approval-dependent tasks.

## Resume commands (Mac zsh)
`cd /Users/jo/work-staging/concierge-integration && git status --short && git log -2 --oneline`
`cd /Users/jo/work-staging/concierge-integration && PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q`
`cd /Users/jo/work-staging/concierge-integration && PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m unittest QA.verification.twenty_bridge_adapter_test QA.verification.social_owner_integration_test -q`
`cd /Users/jo/work-staging/trendi-site/concierge-stack/social-service && cargo test --locked`

## Non-negotiable restrictions
No push, merge, deploy, enabling live messaging/social posting, paid-provider changes, customer data or real account changes without separate approval. Do not move or stop LiveKit or existing services; do not change production DNS. Never print or commit secrets. Never touch `QA/verification/office-shots/`.
