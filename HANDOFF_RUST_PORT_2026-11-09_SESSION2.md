# Handoff: Rust port, session 2 (9 November 2026)

Continues `HANDOFF_CONCIERGE_VERIFIED_2026-11-09.md` (what is *deployed*; unchanged) and the earlier Rust handoff. **Nothing here is deployed or wired into
the Python API.** Boundaries unchanged: no sends, purchases, calendar events, recordings, provider activations or deployment without explicit authorization;
the six real-world acceptance tests remain open.

## Where the work is
Repo `TrendiBizz/Concierge`, branch **`rust/core-port`**, draft **PR #7** into `integration/concierge-v1`. Always `git fetch` first. Authoritative per-module
table: `concierge-stack/core-rs/PORT_STATUS.md` (batches 1-24). Commit trailers/PR text use the attribution lines the harness supplies.

## Done this session (batches 13-24, all gated, mutation-checked, pushed)
13 channel auth / owner knowledge / phone setup / acknowledgements / ingest - 14 crawler (urllib.parse, html.parser rules, RFC 9309 robots, sitemaps, crawl loop,
adds `fancy-regex`) - 15 settings / owner profile / email drafts / tenants - 16 `chat.run_turn` - 17 the 31 request models of `main.py` + helpers - 18 social
bridge - 19 phone relay - 20 outbox worker - 21 booking - 22 calendar connection - 23 request-edge rules - 24 **`concierge-stack/server-rs`**, a real axum +
PostgreSQL server with 4 read-only routes proven identical to Python on a real database (`QA/verification/rust_server_parity.py`, CI job `rust-server-parity`).

## Rules that keep paying off
1. `./scripts/rust-gate.sh` before every push (fmt, clippy `-D warnings`, tests, `--locked`; now four crates incl. `server-rs`). Never pipe it.
2. **Vectors come from the live Python** (`parity/gen_vectorsNN.py` -> `vectorsNN.json`), never typed by hand. Reading the Python and retyping field lists failed
   twice (`ToolRequest.voice_session_token`, `VoiceCopyRequest.session_id`); diff `model_fields` programmatically.
3. **Mutate each new rule once and see a test fail.** Survivors were test gaps four times (e.g. vectors recording state *after* the run, chunk_count never non-zero).
   Equivalent mutants are documented in PORT_STATUS.
4. Python setup: `python3 -m venv V && V/bin/pip install -r api/requirements-dev.txt`; run generators from `api/` with `PYTHONPATH=../QA/verification/shims:.`
   (Python 3.13.18 here; `casefold_table.json`, `html_tables.json`, `ip_tables.json` are interpreter-specific: regenerate with the production Python).
5. A real Postgres is available locally: `apt-get install postgresql postgresql-16-pgvector`, then `initdb` + `pg_ctl` on 55432 (user postgres, password test).
   The Python API applies the schema itself on start-up. The differential harness needs `psql`.
6. New dependency => refresh `hermes-gateway/Cargo.lock` (it path-depends on core); `server-rs` has its own lock.

## Next steps (in order)
1. Watch CI on the last push (`rust-server-parity` is new); fix anything environment-specific (Ubuntu runner Postgres port is dynamic: use `CONCIERGE_TEST_POSTGRES_PORT`).
2. Grow `server-rs` one route family at a time, each proven by the differential harness against the Python API on the real DB: `GET /report/{token}` (HTML),
   `GET /api/v1/calendar/{token}.ics`, `/demo/{slug}`, then `/owner/*` reads (needs the owner-session cookie: `owner_auth` is ported), then writes
   (chat, tools, voice token, leads, appointments) implementing each core `Env` trait (chat, booking, outbox, calendar_connection, phone_relay, acknowledgements,
   ingest) with the same SQL. Workers (outbox, calendar, sla, digests, email secretary) come last, as tasks behind the same traits.
3. Still not ported: `asterisk_bridge` media loop, `llm`/`mailer`/`embeddings` transports, trafilatura extraction, SLA/digest/email-secretary workers' SQL, `hermes_ops` HTTP.
4. Only after route parity: a staged, feature-flagged cut-over plan. Needs explicit authorization; do not deploy.

## Known declined / approximate (all fail closed or `Unsupported`, listed in PORT_STATUS)
Non-ASCII hostnames and IPv6 zone ids (urllib), floats/lists where Python would use `repr`, numeric datetime timestamps, integers beyond 64 bits in request
bodies, relay answer-cancellation timing, host-specific tz files, SQL `WHERE` semantics of fakes (only the server crate checks SQL against a real database).
