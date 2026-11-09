# Handoff: Rust port, Hermes gateway, CI repair (9 November 2026)

Continues from `HANDOFF_CONCIERGE_VERIFIED_2026-11-09.md` (still the authority on what is *deployed*). Nothing in this
document is deployed. The live Python API on the VPS is unchanged. Preserve every boundary in that handoff: **no sends,
purchases, calendar events or provider activations are authorized**; the six real-world acceptance tests there remain open
and need people or providers, not code.

## Where the work is
- Repo `TrendiBizz/Concierge`, branch **`rust/core-port`**, draft **PR #7** into `integration/concierge-v1`. Always `git fetch` first;
  the sandbox checkout is ephemeral. Commit trailers and PR text use the attribution lines the harness supplies.
- Nothing is wired into `api/app`. The Python remains the only running implementation.

## What exists
### `concierge-stack/core-rs` (crate `concierge-core`, ~3,400 lines)
Rust ports of Python logic, each held to **parity with golden vectors generated from the live Python**
(`parity/gen_vectors*.py` -> `parity/vectors*.json`; `tests/parity*.rs` must reproduce every vector). `PORT_STATUS.md` is the
authoritative per-module table (modules, vector counts, documented differences). Ported so far: chunking, quote guard, contact,
unsubscribe tokens, iCal, rate limiter, scoring, SLA text, sending window, booking slots (DST), quotation maths, `fmt_local`,
booking wording, tool specs (generated JSON), lead-capture rules, Twenty payload/URL/delivery id, lead/appointment views,
automation plans, campaign rules (CPython formatter grammar), owner SMS shortening, recording validation (WAV), Google Calendar
`sync_one` state machine (900 scenarios, identical request sequence), sales, tasks, conversation cleaners, owner credentials
(PBKDF2, byte-identical), SSRF guard (1,353 IP + 159 URL vectors), SMS signatures, sender readiness, UTM tagging, system prompt.
**Not ported:** `main.py` HTTP layer (2,133 lines), `phone_relay`, `asterisk_bridge`, `phone_sip`, `device_sms`, `mailer`,
`llm`, `voice`, `tenants`, `crawler`, `ingest`, `evals`, `owner_knowledge`, `owner_onboarding`, `email_drafts`, `enquiries`,
`inbound_email`, `cloudflare_inbound`, `email_secretary`, `social_bridge`, `managed_phone`, `mobile_connections`,
`telephone_recording`, the DB/async halves of every module, and Twenty outcome classification.

### `concierge-stack/hermes-gateway` (crate `hermes-gateway`, library only)
Capability tokens (HMAC, <=15 min, revocable), closed operation allowlist, strict typed plan, policy validator (recipient must
belong to the case, consent/opt-out at execution, quote guard, idempotency + case version, human takeover, approval bound to
exact content, autonomy levels, quiet hours), action/case state machines, idempotent tenant-scoped ledger. 17 acceptance tests
map to `HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md` §11. See its README for what is *not* built.

### VPS Hermes
`scripts/vps/compose.hermes.yml` + `scripts/vps/hermes.sh` (+ section in `scripts/vps/README.md`). One loopback container/volume/port
per business; secrets from `/opt/trendi/shared`; `--mode customer` refuses to start without an operator-verified
`<tenant>.toolsets.yaml`. **Never run against Docker** (no daemon in the sandbox). Unverified: memory headroom, `cap_drop: ALL`
with Hermes's entrypoint, the python3 health check, egress allowlist.

### CI
`.github/workflows/concierge-isolated.yml`: Trivy pinned to action `v0.36.0` / Trivy `v0.76.2` (older Trivy assets 404), `ffmpeg`
installed for the Rust media tests, restore-canary readiness race fixed, new jobs `rust-core-parity` and `rust-hermes-gateway`.
Test fixtures repaired (campaign kill-switch, email-draft retrieval, owner-UI DOM stub, social contract text). Production code unchanged.
**Open:** `static-checks` fails only on Trivy `DS-0002` (no non-root `USER`) in `concierge-stack/agent/Dockerfile` and
`scripts/asterisk/Dockerfile`. Not fixed because neither image could be built or run in the sandbox.

## Rules that cost real time to learn
1. **Run `scripts/rust-gate.sh` before every push.** It runs fmt, clippy `-D warnings` and tests with `--locked` for all three crates, with no
   pipes. Piping clippy through `grep | head` hid its exit status and pushed red CI twice. The gateway depends on core by path:
   changing core's dependencies requires refreshing `hermes-gateway/Cargo.lock` (CI uses `--locked`).
2. **Parity vectors come from the live Python, never typed by hand.** Regenerate with the same interpreter as production
   (`gen_ip_tables.py` data is Python-version specific: CPython adds ranges in patch releases; vectors here came from 3.13.18).
3. **Prove a test can fail.** For each new rule, break it once and confirm a test goes red. This found a missing 300-second boundary case.
4. Python setup for vectors: `python3 -m venv V && V/bin/pip install -r api/requirements-dev.txt`; run generators from `api/`
   with `PYTHONPATH=../QA/verification/shims:.` (see each script's docstring). `pytest -q api/tests` should show 150 passed.
5. Integration suites need a throwaway Postgres 16 + pgvector on `127.0.0.1:55432` (user `postgres`, password `test`); reset the schema between suites
   (`drop schema public cascade; create schema public`). CI runs each of the 15 suites on a fresh database.
6. `unittest.mock`/fixtures must not call the network. Do not run downloaded binaries (the sandbox blocks it); do not widen repo scope.

## Authorization state
The user has now asked for: (a) the Hermes gateway wired in, (b) the parity port finished, (c) "whatever else is needed". That is clear
instruction to add *new, additive, feature-flagged* code paths to the Python API for Hermes, keeping everything off by default.
It is not authorization to change live behaviour, deploy, send anything, or enable Hermes for a customer.
