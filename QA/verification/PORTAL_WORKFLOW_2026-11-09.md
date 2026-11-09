# Business secretary acceptance — 9 November 2026

The seven-part authoritative scope is implemented in one tenant-private workflow. Website voice uses the existing Grok account and browser microphone; optional cellular setup is independent. Owner setup now controls website voice, agreed bookings, local hours, duration, knowledge import and owner notification destinations. Automated email is separately opt-in; manual review remains the default.

## Evidence and limits

- `portal_workflow_unit_results.txt`: 148 API tests, including private/mixed DNS refusal, unsafe redirect refusal, SMS size/link preservation, DST gaps, invalid quotation quantities and permission revocation at delivery.
- `portal_workflow_database_results.txt`: 37 checks against disposable PostgreSQL and the real API. Google and automatic email model responses are fixtures. Two businesses, complete original email, recording consent/access, owner-only destinations, distinct optional acknowledgement, optimistic quotation review and decimal pricing, concurrent bookings, external conflict, ambiguous insert timeout reconciliation, cancellation, manual/automatic email exclusion, revoked permissions and no replay of historical appointments passed. Fixtures cleaned.
- `portal_workflow_browser_results.txt`: owner/viewer business setup, voice and booking permissions, calendar control, quotation draft/pricing/review and logout isolation in headless Chrome with fixture HTTP responses.
- Existing recording browser checks passed: owner/viewer private audio, permitted sharing/delivery, consent flow and logout cleanup. These are fixtures; no SMS/email receipt is claimed.
- Website import permits same-site public HTTPS only, validates every redirect and DNS result, pins the verified address with original TLS SNI, limits bytes/pages/time and embeds before transactional replacement. Existing knowledge survives failures.
- Google authorization uses the existing registered app/callback, separately bound to the current tenant and owner session. Refresh credentials live in a private mounted directory, not database exports, API responses or clones. Calendar booking checks availability, uses a deterministic event ID and requests guest updates. The returned event must match tenant, appointment, attendee and exact time. Pending/conflict/retry is displayed distinctly from synced. Provider invitation request is not proof of receipt. Historical CRM appointments cannot be replayed upon connection.
- Quotations are contact/enquiry snapshots with integer minor units, decimal quantities, explicit tax, line rounding then tax rounding, optimistic edits and owner-only review/status transitions. Nothing automatically sends a quotation.
- Owner notices retain original email or full text/voice dialogue; recording links expire after 24 hours. Long SMS includes a bounded excerpt and private portal/recording links; the complete original remains in CRM/email. Enquirer acknowledgement requires a separate explicit request/readback and channel permission. Device SMS retains native Send confirmation.
- Opted-in email work has bounded attempts, visible held/failed status and owner retry. Delivery rechecks opt-in and permissions. A human-reviewed draft cannot also become an automatic email reply.

## External acceptance boundary

No new real SMS/email or calendar invitation was authorized. Google Calendar must be connected by the owner in the deployed portal before its actual calendar can be queried or changed. End-to-end handset/email receipt and an actual guest invitation require an explicitly authorized real test. Passing fixtures or a queued message is not delivery evidence.

Primary provider contract: [Google event insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert), [availability query](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query), [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server).

## Deployment

Backup prepared at `/opt/trendi/backups/portal-workflow-20261109`: private source archive, database snapshot and API environment. Rollback image `trendi-concierge-api:before-portal-workflow-20261109`. Existing Google application configured privately under `/opt/trendi/shared/calendar`, owned by API uid10001; no owner tokens connected or invitations sent. Deployment results will be appended after verification.
