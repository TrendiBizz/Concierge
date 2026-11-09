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

`tests/acceptance.rs` (17 tests) and `tests/server.rs` (8 tests) maps to the framework's table: #1 duplicates, #3 malformed output, #11 capability
escalation, #12 uncertain sends, #14 takeover, #15 revoked consent, #24 cross-tenant, #25 approval of a different
revision, #26 quiet hours, #30 stale case. Each security rule was checked by deliberately removing it and confirming a test fails.

## The server (`src/server.rs`, `src/main.rs`)

Loopback-only HTTP service. It refuses to start without three **distinct** 32+ character keys (`HERMES_CAPABILITY_SECRET`,
`HERMES_MINT_KEY`, `HERMES_CONCIERGE_KEY`), the same rule as the social service.

| Route | Auth | Purpose |
|---|---|---|
| `POST /v1/capabilities` | mint key | Issue a tenant/case-scoped capability (TTL clamped to 15 minutes; unknown operations refused). |
| `DELETE /v1/capabilities/{nonce}` | mint key | Revoke one. |
| `POST /v1/plans` | capability | Parse, validate and (unless the business is in shadow mode) forward a plan. 400 unreadable, 401 bad capability, 404 unknown case, 409 Concierge refused, 422 policy rejected, 503 Concierge down. |

It talks to Concierge only through `backend::Backend`; `HttpBackend` calls `/internal/hermes/...` in `api/app/hermes_ops.py`,
which is dark (404) unless `HERMES_GATEWAY_ENABLED` and `HERMES_GATEWAY_KEY` are set, re-verifies everything, and only ever creates
human-reviewed drafts or to-dos. **Nothing sends.** `tests/fixtures/execute_bundle.json` is the exact JSON the gateway sends;
both this crate's tests and `QA/verification/hermes_ops_integration.py` use it, so neither side can change the format alone.

## Not built yet (do not assume)

- **Hermes itself is not connected.** Something must mint a capability per run and hand Hermes the token; no such orchestrator exists.
- **The gateway's ledger is in memory** (advisory). Concierge's `hermes_actions` table is the durable, authoritative idempotency record.
- **No owner-portal UI** for takeover, autonomy level or approving Hermes drafts beyond the existing email-draft screen.
- **No booking or quote executor**: those requests become to-dos for a person.
- **Auto-send does not exist**: `auto` is treated as "needs approval".
- **Not deployed.** No Dockerfile or compose entry for the gateway yet; nothing in production calls any of this.
- **Hermes tool restriction is not done.** See `scripts/vps/hermes.sh`: customer mode refuses to start without an operator-verified toolset file.

## Run

```sh
cd concierge-stack/hermes-gateway && cargo test
```
