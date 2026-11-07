# Private CRM bridge event receipt ledger

This is an optional staging-only extension of the existing Twenty bridge. The active host listener and LiveKit/Grok calling stack are unchanged.

## Mechanism
- The Concierge PostgreSQL queue remains uniquely keyed by (tenant_id, event, source_id).
- For queue deliveries, the worker computes SHA-256 of the serialized tenant/event/source tuple and sends it as delivery_id. No PII is in the identifier.
- In the private bridge, BRIDGE_REQUIRE_DELIVERY_ID=1 demands a 64-character lower-case hex delivery ID; BRIDGE_IDEMPOTENCY_DIR identifies a persistent writable local volume.
- Each event is claimed through an exclusive O_EXCL file. A successful person+note response is stored as a durable receipt. An identical replay returns the prior receipt without contacting Twenty. A changed payload with the same ID fails closed.
- Concurrent in-flight requests and incomplete or interrupted receipts return HTTP 409; the upstream worker classifies this as uncertain, requiring reconciliation.
- An existing claim without a completed receipt must never be removed or retried until the operator verifies the real Twenty person, note and note target.
- The bridge still cannot guarantee a transaction spanning person creation, note creation, Twenty, and the local ledger. Never describe this as exactly-once delivery.
- Legacy website form leads without delivery_id continue only on the existing non-strict host bridge; they are NOT protected by the new ledger.

## Activation and backups
The Docker override uses an isolated named volume twenty-bridge-ledger. BEFORE enabling it, include that volume in the encrypted backup + isolated restore drill and prove a completed receipt survives restart and restore. Test lost-volume and stale-claim recovery with a disposable Twenty workspace. Do not run the private overlay against real customer records without staging and authorization.

No live compose changes or services were restarted during this development.
