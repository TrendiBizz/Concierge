# Concierge integration — staging development record

## Scope

This branch integrates the existing widget CSP fix and office assistant work with two experimental feature-flagged components:

1. Email drafts for human review. Never sends on ingest or generation; a separate authenticated approval places one email in the durable outbound queue. It uses existing SMTP settings and is disabled by default (`EMAIL_DRAFTS_ENABLED=false`).
2. Twilio Conversation Relay inbound telephone adapter. Signed Twilio webhook, signed WSS handshake, private number-to-tenant mapping, per-business opt-in and daily cap. It uses existing Concierge chat and Twilio's speech recognition/synthesis; it does not place calls or buy numbers. Disabled by default (`PHONE_RECEPTIONIST_ENABLED=false`, `phone_enabled=false` and numbers inactive).

New tenants also default to `voice_enabled=false` without overwriting any existing tenant choice.

## Verified results (2026-11-07, isolated Mac test environments)

- 52/52 Python unit tests passed.
- Original office/database feature suites: 12 + 21 + 24 + 19 + 63 = 139/139 checks passed.
- Existing office dashboard: 32/32 real Chrome checks passed.
- New email drafts: 25/25 PostgreSQL integration checks and 7/7 Chrome checks passed.
- New Twilio simulated phone webhook/WebSocket: 22/22 checks passed, including late disconnect race check.
- Production server, database and Docker containers were not altered by these tests.

Important: tests use disposable pgvector PostgreSQL on local port 55432 and a test API on port 18082. The host Python 3.15 environment lacks production fastembed; test scripts use `QA/verification/shims` for import-only tests. Do not use these shims to host production embeddings.

## Verified non-goals and blockers

- No SMTP delivery or inbound provider webhook has been connected and tested. The email feature currently requires authenticated **manual ingestion** of incoming messages; true inbox sync and webhook signature validation remain to build.
- AI-generated email replies still need human inspection; the feature is intentionally disabled by default.
- Browser UI uses a shared global admin token, not per-business owner authentication. Tenant data is separated at route/DB level, but the operator token grants access to every tenant: **must implement tenant-scoped owner identities before external customer portal release**.
- Telephone integration is **simulated only**, no real NZ number, real PSTN audio, carrier failure or human transfer tests. No real calls have been made. Proper voice-call privacy notice, consent and Terms/Privacy need legal review.
- Number provisioning currently trusts the global admin to register an E.164 number; ownership should be validated with Twilio before production enablement. Verify Twilio number/Conversation Relay availability and pricing for NZ.
- Genuine conflict in PR #3 (Claude chat provider) vs PR #4 (Grok followups) in README; keep separate, do not overwrite Grok production provider.
- Site product spec `research/PRODUCT.proposed.md` says lead scoring not built, while verified API includes rule-based scoring; reconcile the site's `/concierge` claims and PRODUCT.md approval before launch.
- Site CSP host and hash exceptions require explicit human approval; do not bypass security gate.
- Retention/deletion/privacy and NZ promotional consent wording, Brevo SPF/DKIM/DMARC, phone provider, xAI spending cap, tunnel calendar route, production backups, proper per-tenant identity, audit and rollback still need work.
- No production deployment or merge to main without separate user permission.

## Paths and repo state

- Original (live-adjacent) checkout: `/Users/jo/concierge` (leave intact).
- This isolated development worktree: `/Users/jo/work-staging/concierge-integration`
- Branch: `integration/concierge-v1`
- Base: `lmstudio-autostart` at `3086399`, with local merges of `widget-csp-fix` and `office-assistant`.
- Sensitive live-key backup was moved out of original working tree to a private permissions-600 file under `~/.config/trendi/secure-backups/`. Never print or commit its contents. Whether credentials need rotation still requires audit.
- The GitHub connector is authenticated as `Trendiisales`, cannot read `TrendiBizz/Concierge` via API. The Mac has the Git checkout and can run git locally. No pushes performed for the new integration branch.

## Changes

`api/app/email_drafts.py` new reviewed-email service.
`api/app/phone_relay.py` new Twilio signed inbound Relay adapter.
`api/app/schema.sql` additive tables `email_drafts`, `phone_numbers`, `phone_calls`, tenant defaults.
`api/app/config.py` default-off flags.
`api/app/main.py` authenticated email/phone routes and signed telephony endpoints.
`api/app/tenants.py` opt-in phone settings.
`api/app/chat.py` voice-style dialogue for telephone channel.
`api/static/admin.html` email review/edit/approve/discard tab hidden unless feature enabled.
`QA/verification/email_drafts_integration.py`, `email_dashboard_test.cjs`, `run_email_browser.sh`, `phone_relay_integration.py`, and this README.

## Safe next steps in strict order

1. Make new branch clean and commit all tested changes locally; do not push, merge, deploy or enable sending without explicit approval.
2. Implement authenticated owner roles per tenant and email/phone endpoints with RBAC + invitation and recovery flows; test cross-tenant isolation.
3. Build secured inbound email ingestion from an agreed provider, with provider webhook signature verification, idempotency, sender identity rules and an anti-prompt-injection test suite. Keep approve-to-send feature gated.
4. Build actual phone provider provisioning/ownership checks, voice interruption and hangup handling, transfer-to-human route, timeout and recording/data notices. Test real NZ inbound call and fallback before enablement.
5. Reconcile product spec and website draft copy; secure explicit PRODUCT.md, CSP and legal approvals. Do not deploy.
6. Establish full isolated CI run, dependency lock, secret scanning, restore test, monitoring/alerts, tenant data retention/deletion, spend cap and rollback proof.
7. Stage deployment under an explicit separate user authorization, then pilot with real end-to-end scenarios; production approval separate again.

## Run locally (safe)

```zsh
cd /Users/jo/work-staging/concierge-integration
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
zsh QA/verification/run_email_browser.sh
```

For the database-backed phone suite, start a *new disposable* `pgvector/pgvector:pg16` Docker container on 127.0.0.1:55432 (not the production container), run with `PYTHONPATH=QA/verification/shims:api`, then always delete only that test container.

All deployment/merge/secret-rotation/paid-provider activity requires explicit approval first.
