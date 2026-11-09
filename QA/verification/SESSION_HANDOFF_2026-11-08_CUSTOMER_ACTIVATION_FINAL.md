# SESSION HANDOFF — Concierge customer activation / production certification
**Date:** 2026-11-08 (NZ)
**Priority:** FINISH THE PRODUCT — do not substitute another handoff for implementation.
**Canonical product:** https://github.com/TrendiBizz/Concierge
**Branch:** `integration/concierge-v1`
**Last verified product commit at handoff creation:** `38070856083b12bd4e3f6493ea6990dfaf0ed15d` (this handoff commit will supersede it).
**Mac.hub working copy:** `/Users/jo/work-staging/concierge-integration`
**Public website source:** `/Users/jo/work-staging/trendi-site-web` (branch `concierge-site`); https://github.com/Trendiisales/trendi-site
**Legacy cleanup worktree:** `/Users/jo/work-staging/trendi-site` (branch `concierge-stack`)
**Existing services:** LiveKit/Grok voice, Concierge API, Twenty CRM, Caddy, Hermes, n8n and Redis have previously run. PRESERVE THEM. No production restart or deployment occurred in the latest task.

## 0. NON-NEGOTIABLE OWNER INSTRUCTIONS
- Deliver the **whole customer-facing Concierge product**, including real phone answering/consented recording, texts, authorized email, social account linking/publishing, booking/lead/CRM flow and a simple onboarding GUI. Do not redefine Concierge as merely a chat widget.
- **One source-of-truth product repository**: `TrendiBizz/Concierge` contains voice, Rust social integrations, API, CRM bridge, onboarding, tests and infrastructure. `Trendiisales/trendi-site` is the existing public website/design/SEO only. Do not reintroduce a second backend product tree there.
- Keep existing trendibizz.com pages, the SEO tab and site design intact; avoid destructive changes and unrelated files, especially `QA/verification/office-shots/`.
- Use original implementations against official APIs, not a Postiz source translation. Rust-first social integration; preserve the working LiveKit/Grok voice path rather than replacing it by accident.
- No false completion claims. A simulated OAuth, call, recording, SMS or email does not qualify as a **real provider-certified activation**.
- Earlier approvals in this workstream: do **not** merge, deploy, switch live messaging/social posting, buy numbers/enable billable recording or change paid-provider plans without separate explicit authorization. Source commits/pushes were requested and completed in the last sessions. Seek approval for material live actions but complete all safe work first.
- Full-code delivery, independent testing, concrete results; report progress while doing the work, avoid unnecessary questions or endless handoffs.

## 1. VERIFIED GIT AND ARCHITECTURE STATUS
**Product branch:** `integration/concierge-v1`, commit `3807085` pushed and remotely hash-verified. Earlier:
- `4518562`: 142 tracked voice/social/backend-related files migrated to `Concierge/concierge-stack/`.
- `af50a1d`: repository ownership/backup runtime cutover, restoring encrypted Twenty CRM backup in isolation, voice Dockerfile fix, private runtime copied with checksums, voice virtualenv rebuilt.
- `3807085`: tenant channel permissions, approval controls, send-time revocation enforcement, opt-in recording groundwork, owner GUI and new CI tests.

**Website cleanup branch:** `Trendiisales/trendi-site`, `concierge-stack` at `32456b9` pushed; removed 142 duplicated tracked product files. Public site `concierge-site` worktree was clean at latest inspection. Website candidate SEO gate 21/21; candidate deployment preflight 31/31 using `/tmp/trendi-seo-candidate-bundle/manifest.json`. The older `deploy_known_good/manifest.json` lacks `/seo.html` and `/concierge.html`, so a default preflight against it fails; don't treat this as a missing website page or deploy the stale bundle.

Private (untracked) runtime under `concierge-stack/.env`, `backup.env`, `data/`, `.venv/` — NEVER print values, add to Git or expose customer data. Local prior runtime archived under ignored `concierge-stack/.migration-rollback/site-legacy-runtime-2026-11-07/`. Daily backup (03:15) and monthly restore test (1st 03:45) launchd jobs now call `/Users/jo/work-staging/concierge-integration/concierge-stack/scheduled-run.sh`. Encrypted backup/upload and restore PASS; Twenty restored 121 tables. Verify status before making further changes.

**Important:** `/Users/jo/Concierge` is ANOTHER checkout of the SAME canonical GitHub product, currently on an older `lmstudio-autostart` branch; do not assume it reflects `integration/concierge-v1`. `/Users/jo/work-staging/concierge-integration` is the integration working tree. Do not overwrite the other checkout or merge older branches blindly.

## 2. LATEST TEST EVIDENCE — ALL EXECUTED, NOT FABRICATED
Latest implementation test run (synthetic/disposable, no paid communications):
- 14 isolated verification suites, zero failed, running a fresh disposable pgvector PostgreSQL per suite.
- API `api/tests/test_units.py`: 52 passed.
- Phone + simulated Twilio Recording API: **29/29** including correct tenant phone number, signed webhook, cross-tenant denial, explicit business authorization, caller phrase `I consent to recording`, mock Twilio recording SID, forged callback denied, signed receipt.
- Cloudflare signed inbound email: **17/17** including permission denied before authorization, replay dedupe and prompt-injection inert handling.
- Existing LiveKit/Grok agent: **54** offline tests passed.
- SocialSync: **19** Node tests passed.
- Rust social: `cargo build --locked`, `cargo test --locked`, `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings` all passed.
- Local Python-to-Rust HTTP contract: PASSED using disposable SQLite/fake account credentials and social publishing OFF. Fixed previously stale source path in `QA/verification/social_rust_contract_test.py` to use the canonical repository.
- Owner GUI browser tests: business profiles and seven channel permission toggles, grant/revoke, viewer access denial, logout and no JavaScript errors; passed.
- New `.github/workflows/concierge-isolated.yml` includes authorization/database suites, Rust tests and HTTP contract, SocialSync; YAML parsed locally. **Check remote GitHub Actions execution separately** — workflow edited/committed does not prove CI passed on GitHub.
- Strict repo boundary: `python3 scripts/check-repository-boundary.py --website-root ../trendi-site` PASSED.
- Full evidence: `QA/verification/CUSTOMER_ACTIVATION_VERIFICATION_2026-11-07.md`.

Do not mistake synthetic passing tests for real application/provider authorization.

## 3. WHAT EXISTS IN CODE
- API: `api/app/main.py` and `api/app/owner_onboarding.py`; owner frontend `api/static/owner.html`.
- Tenant auth / RBAC: `api/app/owner_auth.py`; session-bound tenant, owner-only edits.
- Seven owner-declared channel rights: telephone, call_recording, email_read, email_send, sms_read, sms_send, social; `api/app/channel_authorization.py`, schema `api/app/schema.sql`; tenant-scoped audit and revocation.
- Inbound phone: `api/app/phone_relay.py` (Twilio ConversationRelay as a **separate multi-tenant simulated phone path**). Signed Twilio callback/WebSocket, tenant number mapping, per-tenant calls, turn limits; owner telephone consent enforced.
- Recording: explicit consent offer and Twilio Recording REST call + signed callback in `phone_relay.py`, `main.py`; `PHONE_RECORDING_ENABLED=false` by default; no audio download, storage, retention workflow or real live call proof. The caller first utterance must match `I consent to recording`. Metadata-only recording SID/status. Review recording state machine, callback race behavior, privacy and call-prompt handling before any live use.
- Existing working **Trendi-specific LiveKit + Grok** voice agent is at `concierge-stack/agent/agent.py` with `concierge-stack/livekit/` SIP templates; preserved and offline tested. Its business content/config/booking are Trendi-specific, **not yet a tenant-aware production agent**. Do NOT claim Twilio ConversationRelay is the user's earlier working LiveKit/Grok telephony.
- Social: `concierge-stack/social-service/` (Rust), includes tenant scoping, approval queue and LinkedIn/Mastodon OAuth groundwork, plus local tests. `api/app/social_bridge.py` maps owner endpoints to Rust; `api/static/owner.html` has login-popup OAuth UI. Additional major social networks/provider approval/real token lifecycle missing. Publish OFF.
- Email: `api/app/cloudflare_inbound.py`, `api/app/inbound_email.py`, `api/app/email_drafts.py`, `api/app/mailer.py`. Signed HMAC ingress, mapped tenant mailbox, owner-reviewed drafts, no automatic send from inbound. Real Cloudflare route/MX/sending domain not certified.
- SMS: `api/app/sms.py`, `api/app/outbox.py`, Twilio or Android SMS gateway; STOP/consent, owner authorization at inbound and send-time; real sender/grants and send/receive not certified.
- CRM: existing Twenty CRM instance/bridge, lead and appointment pipelines, queue. CRM-side exactly-once/idempotency and independent customer lead routing still require real verification. Don't break existing Twenty.

## 4. REMAINING WORK: ORDER, DELIVERABLES, PASS CRITERIA

### A. Fix integration weaknesses and choose ONE multi-customer voice architecture first
1. Inspect the already tested LiveKit/Grok implementation and production Docker/SIP bindings, then decide the technically viable way to route every customer's verified number into tenant-specific LiveKit rooms and Grok prompts/knowledge/calendar/CRM (preferred: preserve LiveKit/Grok). Do not silently make Twilio ConversationRelay a substitute for Grok voice; if Twilio is used only as PSTN/SIP ingress or recording, document actual signal flow.
2. Introduce **verified tenant identity at call ingress**, tied to owned destination number/trunk, independent of untrusted caller-selected metadata. Map each tenant to its configuration, escalation/transfer, booking, notification and CRM; no customer A data in customer B agent. Require authenticated SIP dispatch and fail closed.
3. Implement operational failover/transfer, quiet/open hours, limits and caller disclosures; multi-customer recording consent + retention/deletion policy, safe logs, signed receipts. Avoid automatic audio capture.
4. Run synthetic 2-tenant isolation; then use a real authorized test number, call each configured business, demonstrate accurate Grok voice dialogue, correct bookings/CRM, transfer, hang-up, rollback and no cross-tenant leaks.
**PASS:** actual signed provider call and LiveKit room logs/recording consent evidence, plus reproducible 2-tenant test results. No real telephone number / provider approval currently established.

### B. Real social customer OAuth
1. Inspect actual configured developer apps, approved scopes, redirect URIs and provider eligibility **without printing secrets**. Decide the smallest essential platform set (LinkedIn, Meta Facebook/Instagram, Google Business Profile, X, TikTok, Bluesky where feasible). Determine genuine official API access, free-tier and app-review constraints.
2. Complete independent Rust provider adapters, authorization code + PKCE where supported, state validation, tenant binding, encrypted tokens, refresh/revoke, permission-denied handling and reconnect flows. Follow provider-specific rules; no passwords scraped; no Postiz source translation.
3. Single owner-facing **Connect account** flow and verified account status; post approval queue, consent, retry/idempotency and revocation. Publishing stays off until operator and test customer explicitly approve.
4. Test each approved provider with a real authorized test account, then disconnect/revoke/relink and verify no cross-tenant access.
**PASS:** real OAuth consent from provider with scoped token proof, profile verification, refresh/revoke, one test approved scheduled post with external receipt where authorized; not synthetic-only. External app approvals may not be available this session.

### C. Customer-owned email and SMS
1. Cloudflare Email Routing/MX and Worker signing for authorized inbound business address; verify actual signed delivery with MIME/attachments safely handled/blocked, tenant mapping and AI prompt-injection boundaries.
2. Authorized outbound SMTP or official provider grant, verified business sender (SPF/DKIM/DMARC), draft review + authorized send, bounced/revoked recipient, unsubscribe and deletion.
3. Verified Twilio/NZ number or approved SMS gateway for customer, signed inbound/outbound, STOP/START, quiet hours, positive/negative consent, reliable delivery receipts and opt-out in queued sending.
4. Enforce per-tenant **provider credentials**, not a shared Trendi sender for all customers. Audit and redaction.
**PASS:** real authorized test messages, receipts, no cross-tenant leaks, stop/revoke preventing subsequent send, repeatable supportable setup. Customer-owned grants are still needed.

### D. Unified end-to-end onboarding and customer activation
1. Polish owner portal into guided setup: business profile, website, customer voice knowledge, phone-number claim, call recording consent/legal text, email/SMS grant, social account linking, CRM integration, billing/activation readiness, each with clear status and one-click test where safe.
2. Separate **declared authorization** from independently checked **provider_verified**, operator review, actual live activation. Current `/owner/onboarding/readiness` deliberately shows all provider_verified=false, active=false. Implement durable verified evidence and operator activation state (with expiry/recheck) only AFTER real tests and appropriate approvals.
3. Register two authorized test tenants and run one complete owner-led onboarding each: role restrictions, phone/Grok routing, recording opt-in/out, email and SMS two-way, social OAuth, approved post, CRM events, ownership isolation, backup/restore and rollback.
4. Confirm website design/SEO and Concierge page access without disrupting trendibizz.com. Run remote CI/security scans, penetration/security review, uptime alerts, database backup restore.
**PASS:** full two-customer acceptance record with timestamps/receipts and clean rollback, published channel checklist, user-approved production cutover.

## 5. EXTERNAL REQUIREMENTS YOU CANNOT SOLVE BY INVENTING SUCCESS
**Minimum user/operator actions** when implementation reaches those gates:
- Confirm accounts and domain control for Trendi developer projects (LinkedIn and Meta app review; other chosen networks). Real customer/test-account consent must be completed by authorized owners in each provider UI. Do not forge reviews.
- Approved NZ telephone carrier/SIP/Twilio number(s) and associated billing approval (may incur actual costs); at least two safely controlled test destinations and a real callback/transfer destination.
- Cloudflare zone/MX/domain owner authorization and intended customer addresses, sender-mail service/domain DNS approvals; approved NZ SMS sender/provider and a test handset.
- Explicit authorization to make real tests, recording and retention policy/legal compliance (NZ privacy and telecommunications rules), and permission to enable production messaging/social publishing or paid provider services.
- Customer-specific CRM and calendar API grants; OAuth/login by each customer where required.
Never place secrets in Git, logs, PR descriptions or the handoff. If a needed access grant is unavailable, fully implement/test the remaining work and state **exactly which external action** is blocking certification.

## 6. START NEXT SESSION IMMEDIATELY (NO REPEATED DISCOVERY)
1. Connect to Mac.hub. `cd /Users/jo/work-staging/concierge-integration`.
2. Read this handoff, `QA/verification/CUSTOMER_ACTIVATION_VERIFICATION_2026-11-07.md`, `concierge-stack/MIGRATION.md`, `api/app/main.py`, `api/app/phone_relay.py`, `concierge-stack/agent/agent.py`, `api/static/owner.html`, Rust OAuth sources and CI.
3. Verify `git status -sb`, remote commit and Docker health; preserve the ignored `QA/verification/office-shots/` folder (not product changes).
4. Verify local source + developer config availability safely by **listing key names/booleans only**. Don't request credentials before checking what already exists. The last inspection found no configured Rust social environment and no `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/phone activation keys in the private `concierge-stack/.env`, though real keys may exist elsewhere; investigate approved secret stores, never copy credentials into code.
5. Start with section A, actual tenant-aware LiveKit/Grok routing and comprehensive consent-safe recording; then B OAuth, C email/SMS, D onboarding. Parallelize independent work only where changes won't conflict.
6. Verify with isolated DB/tests and browser first; validate real provider flows only with authorized accounts. Do not restart existing production services or touch paid integrations by default.
7. Update the tests, documented readiness evidence and CI; commit and push to `TrendiBizz/Concierge` integration branch. Do not merge to main/deploy without approval. Keep the website repo unchanged except separately authorized website-specific updates.
8. **Report DONE only if each real provider channel has verified external receipts**. Otherwise give the precise unverified channel + action needed, not a generic “outstanding” list.

## 7. COMMANDS (macOS zsh, from product root)
```sh
git status -sb
git log -3 --oneline
python3 scripts/check-repository-boundary.py --website-root ../trendi-site
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m unittest QA.verification.customer_authorization_test -q
node QA/verification/owner_onboarding_browser.cjs
concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -q
(cd concierge-stack/social-service && cargo fmt --check && cargo clippy --locked --all-targets -- -D warnings && cargo test --locked && cargo build --locked)
PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python QA/verification/social_rust_contract_test.py
(cd concierge-stack/socialsync/server && node --test)
docker ps --format '{{.Names}} {{.Status}}'
```
**Disposable DB integration:** scripts such as `QA/verification/phone_relay_integration.py` and `cloudflare_inbound_integration.py` target ONLY a throwaway pgvector PostgreSQL on `127.0.0.1:55432` with `postgres:test`. Never run them against the live database. Confirm the port is free, create an isolated `pgvector/pgvector:pg16` container, and tear it down in a trap.

## 8. SCOPE AND HONEST STATUS
**DONE:** consolidated repo, code security hardening, owner permission GUI, simulated phone and recording, synthetic email and social workflows, encrypted backup/restore, local 14-suite verification. **NOT DONE:** certified real provider/OAuth, live tenant-aware LiveKit voice, real recording retention, authorized customer email/SMS and full two-customer onboarding, production deployment.

The next session's instruction is to **FINISH IMPLEMENTATION AND AS MUCH EXTERNAL VERIFICATION AS ACCESS ALLOWS**, not produce yet another premature handoff. This file is the complete continuation specification.
