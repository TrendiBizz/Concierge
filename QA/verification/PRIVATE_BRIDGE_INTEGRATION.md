# Private CRM bridge — prepared integration, NOT deployed

The Concierge API and the existing Twenty CRM run in separate Docker networks.
The existing host lead bridge remains healthy on `127.0.0.1:4410`. Do not
change that listener to `0.0.0.0` or expose it publicly.

## Safe design

The optional `docker-compose.twenty-bridge.yml` adds **one small Node.js
container** that runs the existing, unchanged-by-design lead conversion logic
from `integrations/twenty/bridge/server.js` (only an optional private
Bearer-key check was added). This container joins both existing Docker
networks, publishes **no host ports**, and reads the Twenty CRM key from a
Docker secret. The Concierge API authenticates to the bridge with a different
private Docker secret.

All tenant routing remains in the platform. Only the explicitly configured
Trendi tenant can send leads or appointment events to this shared Twenty
workspace. Other customers use their own CRM/webhook adapters.

## Prepared files

- `docker-compose.twenty-bridge.yml` — optional Compose override
- `scripts/export-twenty-bridge-key.sh` — create git-ignored secrets from
  the existing Keychain (no keys appear in stdout)
- `integrations/twenty/bridge/server.js` — optional strict internal bearer
  authentication when `BRIDGE_INTERNAL_SECRET_FILE` is configured
- `api/app/events.py` — tenant-scoped event queue, explicit confirmation,
  cautious retry for HTTP 429, uncertain outcomes require reconciliation
- `api/app/schema.sql` — persistent `twenty_deliveries` table

## Activation prerequisites (not performed)

1. Explicit permission to update staging Docker configuration, after
   reviewing `docker compose ... config --quiet` and current backup status.
2. Run the secrets preparation script on Mac with Keychain access. Do not
   paste credentials into chat.
3. Confirm the existing networks are named `concierge_default` and
   `concierge-twenty_default`; do not create or merge new permanent networks.
4. Configure `TWENTY_BRIDGE_URL=http://twenty-bridge:4410/lead` and
   `TWENTY_BRIDGE_TENANT_SLUG=concierge` in the operator's git-ignored
   staging environment. This is OFF by default.
5. Test a disposable lead and booking through the actual API -> internal
   bridge -> actual Twenty; confirm only one person and correct notes,
   delete all test records.
6. Test the bridge offline, deny absent/wrong internal credentials, and
   make sure Docker exposes no bridge host port.
7. Verify the delivery queue and manual reconciliation process, test
   rolling back only the new overlay without affecting existing services.
8. Only then consider a production deployment under a separate approval.

## Verification to date

- Existing bridge Node tests: **19/19 pass** (including bearer check).
- `docker compose -f docker-compose.yml -f docker-compose.twenty-bridge.yml
  --env-file /Users/jo/concierge/.env config --quiet`: **PASS**.
- Platform unit tests: **52 pass**; new CRM/owner tests: **12 pass**.
- The full PostgreSQL schema applied twice to disposable PG16: **PASS**.
- Cross-repo Rust HTTP contract test with fake social account: **PASS**.
- **No production Docker changes, live test leads, social posts or messages**.

## Known limitations

The Twenty bridge identifies existing people by email; phone-only duplicates
are not fully idempotent. The platform queue cannot safely retry an ambiguous
response because the lead or CRM note may already exist. Rows are marked
`uncertain` for reconciliation. Complete CRM-side event-id deduplication is
needed before promising exactly-once delivery.

The separate Rust social service still has no production OAuth flow and its
publisher remains disabled. Nothing here enables social posting.
