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
| `concierge-stack/server-rs/` | Rust HTTP server; its own README: "Not deployed, not wired in" |
| `concierge-stack/social-service/` | **Part of the running product** — do not treat as flagged |
| `scripts/rust-gate.sh` | fmt/clippy/test gate for the flagged crates |
| `HANDOFF_RUST_PORT_2026-11-09_SESSION2.md` | port session handoff |
| `QA/verification/RUST_BATCH12_VERIFICATION_2026-11-09.md` | batch 12 verification record |

Nothing here is deleted. The flagging is now complete, including CI.

## Consequence for CI

**Resolved (10 November 2026, second pass).** The four flagged Rust jobs have been **removed** from
`.github/workflows/concierge-isolated.yml`:

| Removed job | Crate | Why it was removed |
| --- | --- | --- |
| `rust-core-parity` | `core-rs` | parallel parity crate, never wired in |
| `rust-hermes-gateway` | `hermes-gateway` | parallel parity crate, never wired in |
| `hermes-gateway-e2e` | `hermes-gateway` | exercises the above |
| `rust-server-parity` | `server-rs` | crate README: "Not deployed, not wired in" |

They no longer burn CI minutes and can no longer drift red for reasons unrelated to the product.

**Deliberately kept**, because these are the running product and not flagged:

| Kept job | What it covers |
| --- | --- |
| `rust-social-locked` | `social-service`, which *is* deployed — also runs the Python `customer_onboarding_integration` suite |
| `socialsync-node` | `socialsync` plus the widget and owner-journey tests |

Do not remove those two as "Rust jobs". A blanket removal of every Rust-named job would drop
coverage of shipped functionality — `rust-social-locked` is named "rust-" but tests the social
service the product runs, and carries a Python QA suite with it.

The Rust *source* is untouched and still present under `concierge-stack/`; only its CI jobs are gone.
If the port resumes, re-add the four jobs from git history (`git show <sha>:<path>`).

The one Python-relevant CI job to keep green is `hermes_ops_integration`
(`.github/workflows/concierge-isolated.yml`), which exercises `api/app/hermes_ops.py`.

## If the port is resumed later

Start from `QA/verification/HANDOFF_RUST_PORT_AND_HERMES_2026-11-09.md` and
`concierge-stack/core-rs/PORT_STATUS.md`, which is the authoritative per-module table. Re-read the
"Rules that cost real time to learn" section before pushing — the gate must never be piped.
