# Rust code — FLAGGED, NOT PURSUED (10 November 2026)

Decision by the user: **ignore the Rust code for now, use Python.** Revisit later if time allows.

## Why no codebase merge was attempted

The Rust work is **not a partial replacement** that can be merged into the Python app. It is a
parallel *parity* implementation that was never wired in. Evidence from this repository:

1. `QA/verification/HANDOFF_RUST_PORT_AND_HERMES_2026-11-09.md` states plainly:
   > "Nothing is wired into `api/app`. The Python remains the only running implementation."

2. The same document's "Not ported" list covers most of the application: `main.py`'s HTTP layer
   (2,133 lines), `phone_relay`, `asterisk_bridge`, `phone_sip`, `device_sms`, `mailer`, `llm`,
   `voice`, `tenants`, `crawler`, `ingest`, `evals`, `owner_knowledge`, `owner_onboarding`,
   `email_drafts`, `enquiries`, `inbound_email`, `cloudflare_inbound`, `email_secretary`,
   `social_bridge`, `managed_phone`, `mobile_connections`, `telephone_recording`, the DB/async
   halves of every module, and Twenty outcome classification.

3. `/README.md` on `main` names the FastAPI/PostgreSQL backend in `api/` as the canonical product
   backend. Only the Rust **social service** (`concierge-stack/social-service/`) is part of the
   running product.

There is therefore no merge point: the crates are separate binaries under `concierge-stack/`, and
only `api/app/` is wired into the deployed service. Merging would mean finishing the port, which is
the work the user is explicitly declining.

## What is flagged (left untouched, preserved as-is)

| Path | What it is |
| --- | --- |
| `concierge-stack/core-rs/` | `concierge-core` parity crate (~3,400 lines), golden-vector tested |
| `concierge-stack/hermes-gateway/` | `hermes-gateway` crate; loopback HTTP service, 17 acceptance tests |
| `concierge-stack/social-service/` | **Part of the running product** — do not treat as flagged |
| `scripts/rust-gate.sh` | fmt/clippy/test gate for the three crates |
| `.github/workflows/concierge-isolated.yml` | jobs `rust-core-parity`, `rust-hermes-gateway`, `hermes-gateway-e2e` |
| `HANDOFF_RUST_PORT_2026-11-09_SESSION2.md` | port session handoff |
| `QA/verification/RUST_BATCH12_VERIFICATION_2026-11-09.md` | batch 12 verification record |

Nothing here is deleted. No Rust code was modified in this session.

## Consequence for CI

`main`'s CI still runs the Rust jobs. If Rust is not being maintained, those jobs will drift and can
fail independently of the Python work. That is a known, accepted cost of flagging rather than
removing. Do not "fix" a Rust CI failure by porting Python code.

The one Python-relevant CI job to keep green is `hermes_ops_integration`
(`.github/workflows/concierge-isolated.yml:38`), which exercises `api/app/hermes_ops.py`.

## If the port is resumed later

Start from `QA/verification/HANDOFF_RUST_PORT_AND_HERMES_2026-11-09.md` and
`concierge-stack/core-rs/PORT_STATUS.md`, which is the authoritative per-module table. Re-read the
"Rules that cost real time to learn" section before pushing — the gate must never be piped.
