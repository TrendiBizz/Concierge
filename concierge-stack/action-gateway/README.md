# Concierge action gateway

First-party Rust policy and planning gateway. No third-party agent runtime is installed or required.
It uses capability tokens, tenant/case binding, a closed operation allowlist and an action ledger.
A model proposes text; Concierge retains permissions and execution. Default shadow mode executes nothing.

Configure three distinct 32-character-or-longer secrets: `ACTION_CAPABILITY_SECRET`,
`ACTION_MINT_KEY`, `ACTION_CONCIERGE_KEY`. Also set `PLANNER_BASE_URL`, `PLANNER_API_KEY`
and `PLANNER_MODEL` explicitly. The model endpoint must use HTTPS or loopback HTTP.
`CONCIERGE_BASE_URL` defaults to loopback port 8000; `ACTION_GATEWAY_BIND` defaults
 to `127.0.0.1:4420` and refuses non-loopback listeners.

The backend uses `/internal/actions` and `X-Action-Gateway-Key`. The compatibility
Python API requires `ACTION_GATEWAY_ENABLED=true` and matching `ACTION_GATEWAY_KEY`.
These routes remain off by default. The deployment descriptor is
`scripts/vps/compose.action-gateway.yml`; the main production stack does not start it.

Run `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, and
`cargo test --locked` here. Tests use fake models/backends only. `tests/model.rs`
checks the direct model protocol on loopback without contacting a provider.

Remaining limitations: the gateway backend still calls the Python compatibility
API until those operations migrate; its in-memory action ledger is not durable
across restarts. No new production cutover is claimed by these local changes.
