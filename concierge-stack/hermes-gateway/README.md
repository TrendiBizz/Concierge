# hermes-gateway

The only path from Hermes's proposals to Concierge's executors. Design source:
`QA/verification/HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md` (§3, §5, §8, §11).

**Trust model.** Hermes is an *untrusted planner*. It receives a short-lived, tenant-scoped capability and returns a typed
plan. Concierge stays the record, the permission boundary and the executor. Nothing Hermes says is believed.

## What is built (library, no deployment)

| Module | Guarantees |
|---|---|
| `capability` | HMAC-SHA256 signed token (`tenant`, `case`, `run`, allowed ops, expiry, nonce). 15-minute maximum lifetime, constant-time verify, revocation by nonce, tampered or cross-tenant payloads rejected. The tenant is derived from the token, never from model output. |
| `ops` | A closed set of ten operations. There is no shell, SQL, URL-fetch or send-mail operation: sending is a policy outcome, not a tool. |
| `plan` | Strict typed plan (`deny_unknown_fields`, size/length/count limits, control characters refused, confidence in 0..1). A model cannot smuggle in a tenant, a capability or any extra field. |
| `policy` | Fails closed; one rejected part rejects the whole plan. Recipient must already belong to the case; consent and opt-out re-checked at execution; channel must be authorized; quoted prices must appear in business evidence (`concierge-core` quote guard); mutations need an idempotency key and the current case version; a human takeover blocks customer effects but never escalation; approvals bind the *exact* tenant/case/channel/recipient/subject/body; autonomy levels (Shadow / DraftReview / AutoRoutine) with routine automation still stopping for sensitive, uncertain, priced or escalated cases; quiet hours via `concierge-core`. |
| `ledger` | Action and case state machines and an idempotent, tenant-scoped ledger. A duplicate request creates nothing, a reused key with different content is a conflict, and an *uncertain* send can only be reconciled, never blindly retried. |

`tests/acceptance.rs` (17 tests) maps to the framework's table: #1 duplicates, #3 malformed output, #11 capability
escalation, #12 uncertain sends, #14 takeover, #15 revoked consent, #24 cross-tenant, #25 approval of a different
revision, #26 quiet hours, #30 stale case. Each security rule was checked by deliberately removing it and confirming a test fails.

## Not built yet (do not assume)

- **No HTTP server.** This is the validation core. The facade endpoints, and the Concierge-side routes they call, are the next step.
- **No Postgres ledger.** `MemoryLedger` is the reference implementation of the `ActionLedger` trait.
- **No Concierge wiring.** Nothing in `api/app` calls this crate; the live Python is unchanged.
- **No token-minting service** or secret distribution.
- **Hermes tool restriction is not done.** See `scripts/vps/hermes.sh`: customer mode refuses to start without an operator-verified toolset file.

## Run

```sh
cd concierge-stack/hermes-gateway && cargo test
```
