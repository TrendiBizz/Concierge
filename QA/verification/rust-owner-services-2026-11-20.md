# Concierge Rust owner services — 20 November 2026

This is local migration evidence, not a production cutover certificate. The production API still uses Python. Hermes runtime and integrations were removed from the local implementation earlier; required legacy database identifiers remain solely for lossless upgrades.

Implemented PostgreSQL/HTTP adapters now cover owner authentication/session management, revenue, products and stock audit, tasks, companies, assignments, saved replies, accountant CSV, business/payment settings, contacts/addresses, timelines/takeover, customer exports, webhook configuration, release notices and assisted install requests. Internal action execution persists its idempotency ledger and drafts/tasks transactionally. Webhook delivery and outgoing mail/SMS are separate workers and are not implied by configuration-route coverage.

The request models are compared against 3,066 fixtures generated directly from the current Python/Pydantic models. Timestamp validation uses speedate and covers dates, timezone offsets, minute precision, numeric epoch seconds/milliseconds and fractional precision. A task validation ordering defect was fixed: invalid lead references must be checked before the application rejects a whitespace-only title. The HTTP regression now compares that error text.

Customer-address deletion serialises on the parent case to preserve the last identity under concurrent deletion. Revenue SQL decodes aggregate bigint sums as text into i128, avoiding overflow when valid individual values sum beyond i64. Contact phone and identity extraction were refreshed against the current Python implementations rather than trusting old migration fixtures.

Provider-free verification uses a uniquely named, disposable loopback PostgreSQL database. It starts actual Python and Rust HTTP servers and checks responses and database effects. It includes tenant/role isolation, concurrent stock changes, concurrent single-use login codes, transaction rollback, durable action replay, address deletion races, export bytes, notification queue contents and per-user release acknowledgement. The suite includes 95 named exact owner comparisons plus the separately asserted service scenarios; 95 is not the total number of assertions. The Rust server creates and reapplies the shared schema without starting Python. Legacy action state is preserved through schema upgrades.

Verified commands:

- `scripts/rust-gate.sh`: formatting, Clippy with warnings denied, and locked tests pass for core, action gateway, social service and server, including the latest install and release adapters.
- `/Users/jo/work-staging/venv-concierge/bin/python QA/verification/rust_owner_parity.py`: passed all owner/service scenarios through assisted installs and release notices. Every test notification remained pending in the disposable outbox; no customer communication was delivered.
- Full canonical Python suite: **1,567 passed, 19 skipped**. The existing social-icon test had hard-coded an older cache version despite newer valid page versions. It now requires a syntactically valid version at least as new as the introduction of the styles. No website HTML was changed.
- Mutation check: replacing the CSS version minimum with `99991231z` made the regression fail. Restoring it produced **10 passing social-icon tests**. Earlier phone-normalisation and friendly-validation mutations were also rejected and restored.

Maintenance replacement includes immediate/hourly voice retention with graceful stop, a one-shot purge CLI, and explicit bounded owner-auth cleanup. Cleanup defaults to dry-run, requires DATABASE_URL, validates batch bounds, preserves active credentials and uses SKIP LOCKED for bounded deletion. Python/Rust comparisons confirm retention cascades and cleanup counts.

Known limitations: Hyper normalises trailing whitespace in HTTP headers differently from the Python server; malformed JSON/content-type and some path/query error shapes need further differential coverage. Route registration alone is not proof of migration. At this checkpoint, 342 mounted Python route/method pairs include 64 Rust registrations, leaving 278 missing; 17 background-task sites and seven voice modules remain unverified. The inventory fails its completeness gate. Rust must not replace production until missing services, workers, voice and operational checks are complete.
