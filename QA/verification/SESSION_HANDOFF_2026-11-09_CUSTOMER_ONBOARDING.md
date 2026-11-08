# Trendi Concierge handoff — customer onboarding and feature confirmation

## Resume here

User requested this handoff after asking to integrate Concierge into the existing trendibizz.com and verify that separate customers can easily add their socials and business data, plus confirm CRM/calendar/appointments/add-ons.

- Product: /Users/jo/work-staging/concierge-integration, repository TrendiBizz/Concierge, branch integration/concierge-v1.
- Product code HEAD before this handoff: 8afb70a (pushed), preceded by 5439aaf and 374630b.
- Website: /Users/jo/work-staging/trendi-site-web, repository Trendiisales/trendi-site, branch concierge-site, HEAD fad74d3 (pushed), clean.
- Product untracked QA/verification/office-shots/ and QA/verification/tiktok-review/ are unrelated. Preserve both; never add or delete them casually.
- Read /Users/jo/.codex/RTK.md and applicable repository instructions before work.

## User scope and permissions

Keep TrendiBizz and the current trendibizz.com. Fold Concierge in as the flagship product while retaining SEO and pentesting pages. One canonical product backend; website remains the marketing source, not a duplicate backend.

Preserve Docker, production services, Twenty CRM, LiveKit/Grok voice, recordings and working social connections. No production deployment, social publishing, paid-provider changes, live calls/messages, or application termination without approval. Commits/pushes are authorized. Do not ask for repeated OAuth retries without identifying an actual failure. User previously approved unloading the idle LM Studio model, which was completed; this is not permission to stop other apps.

## Completed and pushed

### 5439aaf — guided onboarding and customer separation

- Admin Add customer form creates a separate business and private invitation; retrying a failed invitation reuses the existing workspace.
- Single-use 24-hour invitation uses a URL fragment, removed before requests. Password confirmation then automatic sign-in to the correct workspace; no manual business-ID entry required.
- Owner can edit business name/site and existing safe profile fields. Saving a website does not crawl it or activate channels.
- New tenant-scoped /owner/knowledge list/save/delete: paste or review .txt/.md, 100 KB maximum; same title replaces only that tenant's document. Handles Windows newlines. No caller-controlled tenant ID.
- Embedding failures preserve previous knowledge; advisory locks serialize replacement/deletion, and incomplete embedding output fails before deletion.
- Rust store rejects foreign/unknown social account IDs before creating a draft, including mixed owned/unowned IDs.
- Owner logout clears private drafts, identity and invitation fields; session generation prevents late prior-session HTTP/file results from painting another customer's workspace.
- Setup checklist, provider-specific guidance, configured social provider buttons only. LinkedIn guidance distinguishes personal member sign-in from company Page access.
- Concurrent same-name customer creation uses atomic INSERT ON CONFLICT retry. Generated base slug limited to 80 characters for social-bridge compatibility; existing slugs unchanged.
- CI extended for real PostgreSQL/Rust customer journeys and offline client tests.

### 8afb70a — appointment regression and feature audit

- New QA/verification/booking_integration.py proves actual native booking against disposable PostgreSQL: availability, mandatory read-back even if first call says confirmed=true, concurrent same-slot requests create exactly one appointment, per-business separation, booked lead state, hours/window limits, private ICS feed and invalid token denial.
- Added booking test to isolated CI matrix.
- Full results in FEATURE_CONFIRMATION_2026-11-09.md.

### Earlier website integration

- Product 374630b and website fad74d3 connect existing Trendi navigation, Concierge setup/sign-in, branded owner portal and shared widget; SEO/pentesting preserved.
- Website setup request is not automatic customer provisioning; admin creates owner invitation.
- Website candidate passed 10 Node tests, 37 deployment preflight checks and 21 SEO checks in earlier session. Website CI was green then; do not assume current product CI status.
- No website or production deployment occurred.

## Verified status — use precise language

Fresh checks on 2026-11-09 NZDT:
- Production API 127.0.0.1:8000/healthz and staging API 8001/healthz: HTTP 200.
- Rust social 127.0.0.1:4390/health: HTTP 200.
- Existing Twenty bridge 127.0.0.1:4410/health: HTTP 200, configured=true.
- Twenty server/database/worker and existing Docker stack remained running; no restarts.
- Real Twenty authenticated READ-ONLY phone/email filter probes: HTTP 200, synthetic nonmatching results. No customer records printed or changed. This does not certify real write/retry/note behavior for each new customer or exactly-once delivery.

Latest fresh isolated suites:
- Office: 63/63 checks (tasks, sales pipeline, booking-stage automation, weekly summary, calendar and cancellation).
- Lead scoring: 12/12; per-customer scoring/SLA: 21/21; campaigns: 24/24.
- Email drafts: 25/25; simulated phone/recording: 29/29; signed Cloudflare ingress: 17/17.
- Database channel authorization: PASS (isolation, revocation, audit, readiness).
- Native booking concurrency/calendar regression: PASS.
- CRM Node bridge: 27 tests; Python adapter: 10 tests; preserved voice/booking/notification/CRM offline suite: 63 tests; all passed.
- Onboarding implementation verification: 8 actual PostgreSQL/Rust journeys; 18 existing owner tests; 52 Python units; 56 Rust tests; 9 Node client/widget tests, all passed. Rust Clippy warnings denied, fmt, Python compilation and git whitespace checks passed.

Tests used only resource-limited owned disposable pgvector containers at loopback 55432. All owned QA containers were removed. Rust fixture children/temp SQLite were cleaned. Embeddings used deterministic mock vectors; no real social token exchange, publishing, external calendar sync or provider messaging occurred. Node client tests use actual inline scripts in an in-memory DOM, not a real browser.

## Social wording — user explicitly corrected earlier ambiguity

LinkedIn OAuth IS FIXED AND CONNECTED. Scope whitespace/comma issue fixed ae8110f, real success evidence 426bdde. Do not describe LinkedIn OAuth as still broken/unverified. Prior staging evidence has one connected Facebook, Instagram, LinkedIn and TikTok account; LinkedIn token encrypted, granted openid/profile, publishing false. Company Page management and another ordinary customer's consent have not been proved. TikTok connects, but recorded connection is sandbox; production app approval status has not been newly checked. Do not equate a connection bug fix with provider production approval, or confuse those remaining questions with failed OAuth.

## Deployment and browser limitations

New source changes 5439aaf and 8afb70a are NOT deployed. Production API runs older code from /Users/jo/concierge; public owner host still routes isolated staging at 8001. Canonical integration checkout is NOT automatically the live runtime. Native social staging 4390 also was not restarted for the newest store change.

API candidate image concierge-api:trendi-integration-20261108 was built before latest onboarding work and is STALE. Rebuild and source-hash verify before considering any stage rollout. Do not deploy it as though it includes these fixes. Base image concierge-api:oauth-staging-20261108; api/Dockerfile.integration copies canonical app/static after prior dependency-parity verification. Preserve private env/network/mounts and disabled publishing/outbox settings.

Website candidate /private/tmp/trendi-integration-candidate-20261108 is ephemeral. Website build environment /private/tmp/trendi-integration-build-20261108 and threat cache /private/tmp/trendi-security-cache-20261108 may be absent later. See website integration records for reproduction.

Browser Chrome/IAB attempts previously returned explicit origin-approval rejection despite user enabling permissions. No alternate browser/CDP/headless automation was used to bypass it. Latest onboarding has no real-browser visual/accessibility certification. Do not repeatedly retry or circumvent a denied origin.

## Remaining work / recommended next session

1. Confirm remote CI for 5439aaf/8afb70a and resolve real failures; adding tests to a workflow does not mean hosted CI passed.
2. If continuing release preparation, rebuild current candidate and perform authorized isolated staging rollout with rollback and exact source/dependency verification. No production rollout without approval.
3. Browser QA when access is actually available: add two customers, private invitation/password setup, text/Markdown review/save/replacement, role restrictions, sign-out/sign-in isolation and provider callback UI. Avoid repeated live provider consent without a diagnosed need.
4. CRM full write/retry/note and separate customer destinations need controlled authorized live verification. Existing healthy/read-compatible CRM is not proof of every new tenant's end-to-end delivery.
5. Native scheduling/ICS works in fresh tests. Google/Microsoft two-way calendar sync is NOT certified. Live email/SMS/campaign delivery requires actual configured customer providers, permission and receipts.
6. Preserve existing working LiveKit/Grok. New customer-specific phone routing, actual calls, recording audio storage/retention and provider evidence remain separate from simulated Twilio tests; do not present the simulated path as equivalent to live Grok calls.
7. Keep publishing disabled until explicitly approved. Verify ordinary-customer Meta eligibility, TikTok production status and LinkedIn company Page capability only where product requirements need them.
8. Website deployment remains a separate explicit approval step; keep current SEO and pentesting intact.

## Evidence and commands

Read QA/verification/CUSTOMER_ONBOARDING_2026-11-09.md, FEATURE_CONFIRMATION_2026-11-09.md, TRENDIBIZZ_WEBSITE_INTEGRATION_2026-11-08.md, LINKEDIN_SCOPE_CPU_VERIFICATION_2026-11-08.md. Website detail: /Users/jo/work-staging/trendi-site-web/research/TRENDIBIZZ_CONCIERGE_INTEGRATION_2026-11-08.md.

Python: /Users/jo/work-staging/venv-concierge/bin/python, PYTHONPATH=QA/verification/shims:api. Database integration scripts hardcode disposable 127.0.0.1:55432/postgres and synthetic credentials; start ONLY a new owned QA pgvector database there and use a fresh empty DB per suite, then remove it. Never point at live DB.

Rust: CARGO_BUILD_JOBS=1 nice -n 15 /Users/jo/.cargo/bin/cargo test --locked -j 1 from concierge-stack/social-service. Customer journey requires the current Rust binary built first; fixture uses random port. Existing social_rust_contract_test.py hardcodes 4390 and refuses when occupied; do not stop the staging service to run it.

Do not expose .private env files, production databases, macOS Keychain secrets, OAuth codes/tokens or owner invitation links. Read-only Twenty probe obtains its key internally and prints only response metadata. Existing /private/tmp/feature-audit-*.log are ephemeral, not durable evidence.
