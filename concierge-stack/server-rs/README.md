# concierge-server

Rust HTTP server for Concierge. **Not deployed, not wired in; the Python API remains the only running implementation.**

Read-only routes so far: `GET /healthz`, `GET /api/v1/widget-config`, `GET /admin/tenants`, `GET /admin/tenants/{slug}`, plus the owner-portal
origin boundary and wildcard CORS. All decisions come from `concierge-core` (parity-tested against the Python); this crate adds only HTTP and PostgreSQL
(`axum`, `tokio-postgres`, `deadpool-postgres`).

Configuration uses the Python API's names: `DATABASE_URL`, `ADMIN_TOKEN`, `PUBLIC_BASE_URL`, `VOICE_RECORDING_ENABLED`, and `BIND` (default `127.0.0.1:8001`).

Verification: `tests/offline.rs` (in-process) and `QA/verification/rust_server_parity.py`, which starts this server and the real Python API on the same
PostgreSQL and requires identical status, JSON body and security headers for 25 requests (CI job `rust-server-parity`).
Quirks reproduced on purpose: `jsonb` columns other than `business_hours`/`demo_questions` are returned as JSON *text* (asyncpg behaviour), timestamps use
Python's `isoformat()`, and `GET /admin/tenants/{slug}` backfills a missing calendar token exactly like the Python route.
