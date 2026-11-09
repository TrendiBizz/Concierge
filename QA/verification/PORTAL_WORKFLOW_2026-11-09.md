# Business secretary acceptance — 9 November 2026

Implemented, pushed and deployed the seven-part tenant-private workflow. Controlled live owner email, SMS and Calendar tests completed with user authorization. Website voice uses the existing Grok account; optional cellular setup remains independent.

| Requirement | Result and evidence |
| --- | --- |
| Channel ingress | Actual deployed Grok chat and website voice exercised. Signed email/device SMS ingress and full originals checked with real API/PostgreSQL fixtures. External-customer carrier SMS ingress not independently exercised. |
| Business-specific answers | Two-business knowledge/chat isolation passed; actual public HTTPS import and actual Grok chat/voice passed. |
| Original forwarding | Configured owner email/phone, full originals in CRM/email, bounded long SMS with private portal/recording links. Actual owner email arrived; exact full SMS sent and received14:08, user confirmed. Recording consent and private24hour links enforced. |
| Optional acknowledgement | Separate explicit request/readback, recipient/channel permission and declined-request behavior passed DB/API fixtures. No extra acknowledgement sent during limited live test. |
| CRM | Full text/email/voice dialogue, contact/enquiry/task/appointment linkage and role isolation passed. Actual labelled test enquiry and Calendar appointment retained. |
| Calendar | Owner OAuth connected with explicit scope approval; API enabled with approval. Real freeBusy slots, event POST/GET and matching tenant/appointment/time/attendee confirmed. Provider accepted invitation request. Owner is also organizer: separate guest inbox delivery not claimed. |
| Quotations | Contact/enquiry snapshots, decimal quantities/integer minor units, explicit tax and optimistic owner review. Deployed real API browser verified150.02+22.50=172.52 and viewer denial. No automatic quote sending. |

## Verification

150 unit tests and39 disposable PostgreSQL/actual API checks passed. Provider conflict/failure/timeout responses in this suite are fixtures.25 mocked onboarding/quotation and19 deployed owner/viewer browser checks passed. Existing recording browser checks passed. Actual Grok isolated chat and synthetic website voice returned91,680audio bytes and transcript. Disposable live businesses removed with zero outbound messages.

All62 tracked API/static files match deployed hashes; private health200. Public actual Chrome portal/callback200; unauthenticated owner APIs401. Public health intentionally unavailable; VPS public-client403 is not browser portal downtime.

Calendar retries use deterministic event IDs and verify tenant, appointment, attendee and exact times. Ambiguous insert timeout reconciles before retry. Pending/conflict remain distinct from synced; historical appointments do not replay on connection. Website import validates public HTTPS/DNS/redirects and pins address with original TLS SNI, bounds resources and atomically replaces knowledge after embedding. Automatic email is separately opt-in/defaultoff with manual review, bounded attempts, held/failed/retry states and delivery-time permission checks.

## Controlled live results and correction

CONCIERGE-20261109-RECEIPT-V1 reached actual owner inbox and handset. Initial test exposed duplicate owner notices: scoring reloaded a row and lost an ingress dedupe flag. Two emails arrived before correction. Commit6e53fc4 preserves the flag before scoring; red/green regression and exact two-channel queue count passed; correction deployed. Failed native-confirmation SMS jobs retained. Explicitly approved SMS-only retry succeeded: outbox10, Messages receipt1B620D3E-2487-4A10-822E-804E73607AA3. User screenshot confirms sent/received exact full body14:08. No email resent.

Actual Calendar test used temporary in-memory test hours, not permanent settings. Appointment073eabec-9583-458a-a7ce-50dcff100fd3 synced; event15adbee1b80650dfa043382060047f8fbf4dbde10a6c7d842b698e422156bd2b confirmed for10November10:00–10:15AM Auckland; invitation_state provider_requested. Extra confirmation/reminder messages deliberately suppressed for this synthetic appointment; outbox0. Real provider check is distinct from fixture verification of full booking readback/CRM/notification sequence.

## Deployment and setup boundaries

Pushed source b7b3b04,13dc1ac,6e53fc4 on integration/concierge-v1. Live image sha256:e106c65dcd8b973e2158845261a3f723650c9386629ce0d13044547c886b2ac9; healthy. Backup /opt/trendi/backups/portal-workflow-20261109 contains prechange source/database/environment; rollback image trendi-concierge-api:before-portal-workflow-20261109. API/social recreated together. Calendar credentials remain private mounted files, never committed.

Canonical owner admin@trendibizz.com connected as Google test user. App remains Testing: this verifies owner integration, not unrestricted customer OAuth launch. Each business needs its own knowledge, account connection, hours and permissions. Public booking remains OFF because real hours are unset. Mac native Send confirmation retained. Outside-customer incoming SMS, separate guest inbox delivery and human microphone conversation are not inferred from fixtures/synthetic audio.

Evidence: portal_workflow_unit_results.txt, portal_workflow_database_results.txt, portal_workflow_browser_results.txt, portal_workflow_deployed_browser_results.txt, portal_workflow_live_results.txt, portal_workflow_calendar_live_results.txt, portal_workflow_controlled_receipt_results.txt and portal_workflow_deployment_results.txt. Completed task tabs closed; personal tabs preserved.
