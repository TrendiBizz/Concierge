# Customer-mode Hermes and gateway on the box, 2026-11-17

Evidence (tool output):
- `deploy-api.sh` and `sync-tooling.sh` ran; `verify-deploy.sh` -> OK. `tenants.daily_summary` column exists on the box.
- `hermes.sh toolsets-install --tenant trendi-support`: scratch-volume proof showed only todo, memory, session_search.
  `docker exec hermes-trendi-support hermes tools list --platform api_server` confirms the same three on the live container.
- DEFECT 1: `hermes-trendi-support` crash-looped (restarts=9). Cause: `cap_drop: [ALL]` in `compose.hermes.yml` stopped the s6
  entrypoint (`s6-applyuidgid: unable to set supplementary group list`, then `can't cd to /opt/data`). Fix: `cap_add: [CHOWN, SETUID,
  SETGID, DAC_OVERRIDE, FOWNER]`, `no-new-privileges` kept. Proof: container Up (healthy), tools list as above.
- DEFECT 2: gateway image build failed: `hermes-gateway/Cargo.lock needs to be updated but --locked was passed`. Cause: `core-rs` gained
  deps (loopback telephone shell) and the gateway lock was never refreshed. Fix: lock regenerated, no existing version bumped,
  `cargo test --locked` 31 passed. Also: the box release had no copy of `concierge-stack/{core-rs,hermes-gateway}` sources current
  enough to build, so both were rsynced (excluding `target`) into `$PRODUCT/concierge-stack/`. These dirs are NOT covered by
  `verify-deploy.sh`; a future sync script should include them.
- `gateway-start` ok (127.0.0.1:4420, healthz 200), `gateway-connect --yes` appended HERMES_GATEWAY_* to api.env, api+social recreated
  together via `redeploy-api.sh` (social reachable).
- Shadow run: `gateway-run <trendi-support tenant> <nil case>` -> `{"error":"case_not_found"}`: gateway authenticated to Concierge and
  was answered by it. `trendi-support` has no cases, so no full planning run has happened yet (nothing sent, no data written).
- Not mutation-checked: defects 1 and 2 are infrastructure, not unit-tested.
- Left unchanged on purpose: `trendi-auxiliary-hermes-1` (internal, broad tools). `stable` image tag was pulled (same v0.23.0 as the
  pinned internal digest); pin `HERMES_IMAGE` to a digest before relying on it.
