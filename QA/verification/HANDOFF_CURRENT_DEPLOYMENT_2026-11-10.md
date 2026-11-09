# Concierge handoff — 10 November 2026

Read this first for current deployment state. Read
HANDOFF_CONCIERGE_PORTAL_WORKFLOW_2026-11-09.md for the complete seven-requirement
product mandate. Its older implementation-gap inventory predates PR9/PR10;
inspect current main before treating any of those gaps as still missing.

## Objective and scope

Every business has a separate Concierge portal, knowledge/Grok receptionist,
contacts, CRM, calendar, quotation records and owner notification destinations.
The seven requirements are: receive voice/text/email; identify channel; answer
from own business information; forward original enquiry to owner; offer optional
acknowledgement to enquirer; retain full CRM dialogue and handle agreed bookings,
owner calendar and enquirer invitation; provide CRM Quotations.

Website/portal browser voice is independent of cellular SIP. The owner's saved
mobile is a notification destination. Spark belongs only to Jo's business.
Actual carrier calls are an optional separate connection; zero SIP numbers is
not evidence website voice cannot work. Use the existing paid Grok account.

## Exact completed state

Workspace /Users/jo/work-staging/concierge-integration, branch main.
Origin git@github.com:TrendiBizz/Concierge.git.
Application code main b35614c includes PR9 and PR10. Pushed follow-up ea606a496a98c175aa0e31934c7ef42ae7b59dc4 adds configuration docs, build revision label
and deployment evidence; no application behavior changes in that commit.

Production API was stale even though main was merged. Rebuilt API from current
main, deployed tracked API/static/locked dependencies, preserved existing private
env and production Compose, recreated API AND social for their shared network
namespace. Both became healthy. Running image:
sha256:7a16174bc7ccb01f68fa27de9608b4297626b80368af88b4523fe9b8d55ac2ae
Image revision label b35614c. All67 application/static file hashes matched main.
customer_cases migration present; private /healthz ok.

PHONE_RECEPTIONIST_ENABLED is now true; existing XAI_API_KEY preserved;
PHONE_VOICE_PROVIDER=grok; XAI_SIP_CONNECTIONS={} (no fictional mapping).
No tenant line enabled or number invented. Database audit:3tenants,
0phone_numbers,0phone_enabled tenants,1telephone authorization. Authenticated
xAI GET /v2/phone-numbers returned200,0numbers,no further page.

Added .env.example phone settings, scripts/vps/PHONE_SETUP.md, source revision
Docker label and README build/deploy instructions. Production reads private
/opt/trendi/shared/api.env, not .env.example.

## Verification and limits

356 Python tests passed in12.95seconds. scripts/rust-gate.sh GATE-ALL-OK for all
four crates; log /tmp/concierge-rust-gate-20261110.log. Origin owner UI200,
unauthenticated readiness401, unknown SIP route503. Public Python HTTP probe
received Cloudflare403/error1010 before the application; do not claim public-edge
acceptance from origin checks. No browser task tabs opened during this work.

No real incoming carrier call or delivery test was performed. No number bought,
account opened, authorization fabricated or external message sent. Existing
permissions, native SMS Send confirmation and per-business consent remain.
Queued is not delivered; config-present is not live carrier proof.

xAI can register an existing carrier/PBX number through API, so console access
is not intrinsically necessary. Existing team has no registered number to reuse.
The API cannot provision new xAI public numbers. An actual compatible ingress
number/trunk, allowed SIP sources or digest, genuine returned signing secret,
private webhook mapping, enabled own-tenant row and real call acceptance are
required for cellular SIP. No new paid service/number purchase was authorized.
Do not hold the website portal workflow hostage to this optional carrier gate.

## Production and recovery

VPS152.42.239.240; SSH root with repo-local private key Concierge, BatchMode,
IdentitiesOnly, StrictHostKeyChecking. Never print/stage that key or env secrets.
Release /opt/trendi/releases/20261108-vps/product (not a Git checkout).
Compose scripts/vps/compose.yml with --env-file /opt/trendi/shared/compose.env.
Secrets /opt/trendi/shared (private). Always recreate social with API.

Backup /opt/trendi/backups/main-api-20261110 contains source-before.tgz,
api.env.before, concierge-before.dump, image-before.txt and build.log.
Rollback image trendi-concierge-api:before-main-api-20261110. Additive schema was
applied; preserve database data during app rollback. Do not run destructive
fixture/reset scripts against production.

Detailed evidence: MAIN_API_DEPLOYMENT_2026-11-10.md.
Optional carrier instructions: ../../scripts/vps/PHONE_SETUP.md.
Latest broader engineering evidence: HANDOFF_PROVIDER_COMPLETION_2026-11-10.md
and HANDOFF_RUST_PORT_AND_HERMES_2026-11-09.md.

## Next runnable work

1. Fetch/read current main and inspect existing portal tests and code before
   changing anything. PR9/PR10 introduced case timeline, provider readiness,
   correct follow-up/reply isolation and phone conversation copies.
2. Verify the seven-step portal workflow against current main and current running
   release, with each result marked implemented/tested/live/unverified. Fix actual
   gaps using existing business settings/tools/CRM/calendar paths. Include two
   businesses and correct owner/enquirer recipients, retry deduplication, consent,
   actual calendar/invite effects and Quotations. Historical unit counts are not
   proof of the whole service.
3. If user specifically wants carrier calls, use the exact genuine SIP prerequisites
   above. Continue all independent portal work while obtaining any indispensable
   carrier input. Existing number registration via API is available once real
   carrier details exist. Never turn a personal notification phone into a fake DID.
4. Test, deploy with rollback and verify effects; commit/push work. Keep checkpoint
   current. Give concise progress without ending on routine errors. For an actual
   external dependency, prepare the concrete integration and request only the
   smallest missing action while finishing everything else authorized.

## Continuation command

Continue /Users/jo/work-staging/concierge-integration/QA/verification/HANDOFF_CURRENT_DEPLOYMENT_2026-11-10.md. Implement and verify the seven-step business-specific portal secretary workflow on current main. Diagnose, fix and retest routine failures; keep working through status questions. Complete independently actionable work before asking for a genuinely missing input. Preserve consent, real delivery evidence and current authorizations. Commit and push verified changes, report deployed versus source state accurately, and stop immediately if I say STOP.

## Preserved unrelated files

Four untracked Hermes handoff/research/audit files under QA/verification,
office-shots/ and tiktok-review/ were left untouched. Do not blanket-stage them.
This handoff does not start a new chat or archive this unfinished objective.
