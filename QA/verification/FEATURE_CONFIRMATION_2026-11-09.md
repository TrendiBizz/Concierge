# Concierge feature confirmation — 2026-11-09 NZDT

Branch integration/concierge-v1, following 5439aaf. Read-only production inspection and fresh disposable tests; no live writes, deployment, calls, mail, SMS or social publishing. Production and staging API /healthz both HTTP 200; Rust social /health HTTP 200; existing Twenty bridge /health HTTP 200, configured=true. Twenty server/database/worker and other existing Docker services remained running.

## Current CRM confirmation

Real Twenty REST read-only probes for email and composite phone filters returned HTTP 200 with expected empty synthetic matches. These confirm authenticated real API compatibility; no customer data printed or changed. Existing bridge health is good. Fresh bridge Node tests: 27 passed; Python bridge adapter: 10 passed; preserved voice/booking/notification/CRM offline suite: 63 passed. Live lead/person/note write-and-retry reconciliation and independent customer CRM destinations are NOT certified by read-only probes. Do not promise exactly-once CRM delivery.

## Fresh isolated database results

Each suite used a new empty database in an owned, resource-limited ephemeral pgvector container on loopback 55432. Outbox disabled. The container was removed afterwards.

| Suite | Result | Coverage |
|---|---|---|
| office_integration | 63/63 | Tasks, sales pipeline, booking-stage automation, weekly summary, calendar feed and cancellation, tenant token handling |
| score_integration | 12/12 | Lead scoring, reasons, alert content, booking score and reports |
| phase3_integration | 21/21 | Per-business scoring overrides and response-time/SLA alerts |
| campaign_integration | 24/24 | Campaign queue, filters, authorization and opt-out behavior |
| email_drafts_integration | 25/25 | Scoped draft review, sending checks and inbound handling; simulated delivery |
| phone_relay_integration | 29/29 | Signed phone path, tenant mapping, recording authorization/consent/callbacks; simulated Twilio |
| cloudflare_inbound_integration | 17/17 | Signed inbound email, replay dedupe, permissions and injection boundary; simulated ingress |
| channel_authorization_db_integration | PASS | Tenant isolation, revocation, audit and readiness |
| booking_integration (new) | PASS | Real native availability/booking and calendar routes, described below |

New booking test executes the actual native booking function against PostgreSQL. It proves that a first-call confirmed=true cannot bypass read-back, no appointment exists until confirmation, two concurrent confirmed requests produce exactly one booking, booked slots disappear only for that business, a separate business retains availability, the resulting lead is booked, out-of-hours/out-of-window requests fail, the appointment appears in its private ICS feed only, and an invalid calendar token returns 404. No external calendar synchronization or notifications are implied. Added this regression to CI.

## What can and cannot be claimed

- Native appointment scheduling and private calendar feeds: fresh integration verification passed. This is not verification of Google/Microsoft two-way calendar sync.
- CRM: existing service/bridge available, real read-only API works, adapter logic passes. Full real write path for every future customer still requires verification.
- Customer workspace onboarding/social-data separation: 5439aaf recorded separate owners/viewer, knowledge/RAG, OAuth-state and draft isolation, private invitation setup and session cleanup. Source changes remain undeployed.
- Website chat/knowledge, tasks, pipeline, scoring, follow-ups, reporting and campaigns exist; database/offline regressions above pass. This does not imply each optional channel is currently enabled for each tenant.
- Existing LiveKit/Grok path preserved; new customer phone routing and live recording/storage/retention remain separate from simulated phone tests.
- Email/SMS and campaign deliveries require configured customer providers/authorization and real receipts. No live delivery was attempted.
- Facebook, Instagram, LinkedIn and TikTok have prior real staging connection evidence. LinkedIn OAuth succeeded; company Page access was not proved. TikTok connection evidence is sandbox. Publishing stays disabled.
- Website SEO and pentesting service pages were preserved in the separate website integration. This audit did not execute a live penetration test or deploy website changes.

The honest status is built and regression-tested core workflows with healthy existing services, not universal live activation of every add-on for every customer. Production runs older code than this integration branch; no new onboarding code was rolled out by this audit.
