# Concierge secretary — verified deployment handoff

9 November 2026, Pacific/Auckland. This handoff records the implemented outcome; the earlier authoritative scope remains the requirements reference.

## Start here

Read PORTAL_WORKFLOW_CHECKPOINT.md and PORTAL_WORKFLOW_2026-11-09.md in this directory before continuing. Preserve their exact send/event identifiers. Continue in the same chat unless the user requests another.

Workspace: /Users/jo/work-staging/concierge-integration. Branch: integration/concierge-v1. Remote: git@github.com:TrendiBizz/Concierge.git. Runtime source through6e53fc4 is deployed. Evidence8b52ab3 and checkpoint2f9e17a were pushed; this handoff is documentation only and needs no container rebuild.

## Delivered and verified

Seven-part business-private secretary workflow implemented: channel ingress and business knowledge, original owner forwarding, separate requested acknowledgements, complete CRM linkage, Calendar availability/event/invitation request, and reviewed quotations. Website Grok voice is independent of optional cellular setup.

150 unit tests,39 actual API/PostgreSQL checks,25 mocked onboarding/quotation browser checks and19 deployed owner/viewer checks passed. Actual Grok isolated chat and synthetic website voice passed. All62 tracked API/static files matched the deployed image; private health200. Actual public Chrome portal/callback200 and unauthenticated owner APIs401.

Controlled owner email arrived. Initial duplicate owner notices exposed a scoring reload bug, corrected and deployed in6e53fc4 with regression coverage. One reconciled SMS-only retry reached SENT with a verified Messages receipt; user confirmed exact full message sent/received at14:08. Google OAuth connected after explicit approvals; Calendar API enabled. Real freeBusy and event creation/readback passed. The retained labelled test event is10November10:00–10:15AM Auckland. Do not send or recreate these tests; exact identifiers are in the checkpoint and receipt evidence.

## Deployment and recovery

VPS152.42.239.240, release /opt/trendi/releases/20261108-vps/product. Live image sha256:e106c65dcd8b973e2158845261a3f723650c9386629ce0d13044547c886b2ac9. Compose scripts/vps/compose.yml with /opt/trendi/shared/compose.env. Recreate API/social together. Backup /opt/trendi/backups/portal-workflow-20261109; rollback image trendi-concierge-api:before-portal-workflow-20261109. Private credentials stay under /opt/trendi/shared; never print or commit key/env/token files.

## Remaining setup and acceptance boundaries

- Real owner business hours remain unset and public booking remains OFF. Obtain actual hours before enabling public bookings.
- Google app remains in Testing with the canonical owner as an approved test user. General customer OAuth rollout still needs production/verification preparation; do not claim unrestricted launch or change publication status silently.
- Each business supplies its own knowledge, destinations, account connections, hours and permissions. Spark settings must not transfer to other customers.
- Native Mac SMS Send confirmation remains required. Outside-customer incoming carrier SMS was not physically exercised. Separate guest inbox delivery was not proven because the authorized Calendar recipient is also the organizer. Human microphone dialogue is not inferred from synthetic audio.
- No further sends, purchases or calendar events are authorized by this handoff alone. Preserve prior finite authorizations and avoid replay.

Completed task tabs closed, personal tabs preserved. Disposable fixture database and credentials removed. Unrelated untracked QA/verification/office-shots and tiktok-review preserved. No active test job or unfinished browser form remains.

## Next work

No pending implementation change is required for this verified deployment. If continuing toward customer launch, first collect real booking hours and prepare Google OAuth production review, then obtain specific authorization for any additional physical inbound SMS or separate guest invitation acceptance test. Keep implementation, provider acceptance and actual recipient receipt distinguished in reports.
