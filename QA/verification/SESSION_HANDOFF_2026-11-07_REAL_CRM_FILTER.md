# Trendi Concierge continuation — CRM real-API read-only compatibility — 2026-11-07

## Worktrees and safety
- Platform: /Users/jo/work-staging/concierge-integration, branch integration/concierge-v1.
- Site: /Users/jo/work-staging/trendi-site, branch concierge-stack.
- Existing LiveKit/Grok voice system and running services left untouched.
- QA/verification/office-shots/ is unrelated, untracked and untouched.
- No push, merge, deployment, Docker restart, phone call, social publish, SMS, email, or paid provider change.

## Confirmed current work
- Read SESSION_HANDOFF_2026-11-07_CRM_PHONE_DEDUPE.md and main site HANDOFF.md.
- Starting local CRM bridge /health returned {ok:true, configured:true}.
- Local Twenty web UI responded; UI response is not an API health test.
- Added QA/verification/twenty_readonly_filter_probe.mjs, which reads a key locally from macOS Keychain without printing it and queries the real Twenty /rest/people endpoint with synthetic non-matching values. It performs GET only.
- Actual Twenty v2.56.0 accepted both the NZ composite phone filter and email filter (HTTP 200); both returned {data:{people:[]}}. No customer records returned or changed. This validates syntax/response envelope only, NOT real phone-match data correctness.
- Hardened bridge findByEmail: malformed list/missing IDs fail closed instead of creating a person.
- Added regression test for malformed email response.
- Node bridge tests: 22 passed, 0 failed.
- Concierge mocked owner+CRM integration tests: 16 passed, 0 failed.
- git diff --check passed.

## Outstanding blockers — NO launch certification
1. CRM: disposable create/retry/note tests on real Twenty need separate authorization; dedupe still lacks durable CRM-side event-id enforcement. Existing platform queue quarantines ambiguous responses. Do not promise exactly-once.
2. OAuth: genuine consenting provider authorizations and callback domain/app approvals; social connector coverage incomplete, publisher off.
3. Voice: existing LiveKit/Grok previous live call is proven, but per-tenant PSTN routing, consented audio recording, and real multi-tenant isolation checks still unproven.
4. Inbound Gmail/IMAP/SMS/telephony: customer-scoped grants, consent, audit and revocation flows, actual provider end-to-end validation.
5. Unified onboarding and customer portal provisioning, CRM/network deployment, website/SEO final approval, legal/provider permissions.
6. Private Docker CRM overlay requires approval; do not activate without backups, isolated staging, security review and multi-tenant testing.

## Verification re-run
cd /Users/jo/work-staging/concierge-integration
node QA/verification/twenty_readonly_filter_probe.mjs
node --test integrations/twenty/bridge/test/bridge.test.mjs
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m unittest QA.verification.twenty_bridge_adapter_test QA.verification.social_owner_integration_test -q
git diff --check
git status --short

## Next safe work
Implement bridge-level durable source-event ledger only with an explicit source id, an atomic claim, replay result storage, and multi-process tests. Do not conflate this with Twenty transactional exactly-once. Add provider OAuth sandbox journeys, tenant separation tests and secure onboarding without enabling live publishing. Preserve all existing services.
