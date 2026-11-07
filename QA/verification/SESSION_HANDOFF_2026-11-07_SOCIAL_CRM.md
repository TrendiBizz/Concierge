# Concierge integration: social and CRM implementation handoff
Date: 2026-11-07

See also `/Users/jo/work-staging/trendi-site/concierge-stack/HANDOFF.md`
for the full combined platform status and unfinished dependency order.

Branch: `integration/concierge-v1`.
Base before changes: `d591d34`.

Implemented locally, no deployment:
- `api/app/social_bridge.py` owner-protected tenant-scoped interface to the
  independent Rust social service. Config default off, browser never sees keys.
- `api/static/owner.html` social drafting and approval display; requires
  authenticated tenant owner/editor, no real social account connection.
- `api/app/events.py`: optional Twenty payload conversion and durable delivery
  worker with no blind retries on uncertain outcomes.
- `api/app/schema.sql`: additive idempotent `twenty_deliveries` table.
- `api/app/automation.py`: persist lead and booking delivery records.
- `api/app/main.py`: social routes with current owner RBAC; optional Twenty
  background worker. `api/app/config.py` defaults keep everything off.
- Offline tests: 52 platform unit, 8 CRM, 4 social owner, real HTTP cross-repo
  disposable contract. PostgreSQL schema idempotence test passed twice.
  Owner JavaScript syntax passed.

Required before activating:
- Private bridge transport across existing Docker networks; NEVER simply
  expose the host bridge publicly.
- Official OAuth, customer social account connection, real consent and scopes.
- Tenant-protected customer approval replies from authenticated channels.
- Real social network pilot accounts, live CRM verification and provider approval.
- Secret setup in git-ignored operator env; do not share keys in chat.
- Optional `TWENTY_BRIDGE_URL` and `TWENTY_BRIDGE_TENANT_SLUG` MUST target
  exactly the intended Trendi tenant and a secure internal transport.
- `SOCIAL_SERVICE_ENABLED` stays off until operator acceptance and deployment.
- Production merge, push, external messaging, provider changes and live calls
  need separate approval.

Do not touch unrelated untracked `QA/verification/office-shots/`.
Do not create any new GitHub repo or use Postiz source as a code template.
