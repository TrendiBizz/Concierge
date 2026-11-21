# 2026-11-21 — Podman healthcheck timestamp parsing, startup retry, and API/social restart coupling

## Incident
At 18:00 NZDT (05:00 UTC) on 2026-11-21, the scheduled Concierge health check on `152.42.239.240` sent an alert email:
- `FAIL container:trendi-api-1: Up 2 seconds (starting)`
- `FAIL container:trendi-social-1: container missing`
- `warn sms:inbound` (expected status-only warning; paired phone has never delivered an inbound SMS)

## Cause
1. **Podman `StartedAt` format broke `recently_started()` and `deploying()`:** Podman 4.9.3 formats container `StartedAt` in Go's `time.Time.String()` format (`2026-11-21 05:00:00.617192387 +0000 UTC`) rather than RFC3339 (`...Z`). `datetime.fromisoformat(...)` in `scripts/vps/healthcheck.py` raised `ValueError`, so `recently_started()` always returned `False`. That disabled both the 10-minute startup warming grace for `(starting)` containers and the 10-minute `deploying()` grace window.
2. **Single-shot container snapshot caught mid-swap:** `redeploy-api.sh` started `trendi-api-1` at `05:00:00.617 UTC` and reattached `trendi-social-1` at `05:00:02.855 UTC`. Cron ran `healthcheck.sh` at `05:00:01 UTC`, taking a single snapshot with no retry while `trendi-api-1` was `(starting)` and `trendi-social-1` was in the 2.2-second recreate window.
3. **Cron alert fallback bypassed deploy grace:** `healthcheck.py` exited `1` even when `deploying()` suppressed alerting, causing cron's `healthcheck.sh || alert.sh` fallback to send an alert email immediately on the first transient failure.
4. **Solo API recreate left in token-rotation script:** `scripts/vps/rotate-cloudflare-token.sh` recreated only `api` directly instead of calling `scripts/vps/redeploy-api.sh`, which fails or detaches `social` (`network_mode: service:api`) under Podman. `scripts/vps/redeploy-api.sh` also lacked `--no-build`, explicit `/healthz` timeout failure, `NetworkMode` verification, and social probe retries.

## Fix
- `scripts/vps/healthcheck.py`:
  - Added `parse_container_timestamp()` supporting both Go `time.Time.String()` (Podman) and RFC3339/ISO-8601 timestamps; wired `recently_started()` through it.
  - Added short retry loop in `check_containers()` (up to 3 attempts, 5s apart, zero delay when all containers are healthy/running) to absorb brief startup and recreate transitions.
  - Added `social:reachable` check in `check_sidecar()` so a detached `social` container cannot hide behind a green container list.
  - Exited `0` during active `deploy grace` in scheduled alerting mode so `alert.sh` honours the same grace window, while keeping `--no-alert` runs strict (exit `1` on any failure).
- `scripts/vps/redeploy-api.sh` & `scripts/vps/restart-api.sh`:
  - Added `--no-build` flag to `redeploy-api.sh` and added `restart-api.sh` delegating to `redeploy-api.sh --no-build`.
  - Force-recreated `api` and `social` after removing `social`, normalised hash-prefixed names for both, failed explicitly if `/healthz` times out, verified `trendi-social-1` `NetworkMode` matches `container:<api_id>`, and retried the internal social reachability probe briefly.
- `scripts/vps/rotate-cloudflare-token.sh`:
  - Replaced direct API-only recreate with `scripts/vps/redeploy-api.sh --no-build`.
- `api/tests/test_healthcheck_containers.py`:
  - Added regression tests covering Podman timestamp parsing, `recently_started`, retry recovery during mid-swap, warming grace, `social:reachable` detection, `main()` deploy-grace vs `--no-alert` exit codes, and a repo-wide guard ensuring no script restarts `api` without `redeploy-api.sh`.

## Proof
- Mutation check: temporarily reverting `recently_started()` to raw `datetime.fromisoformat(...)` failed `test_recently_started_recognises_podman_go_timestamp` and `test_container_still_starting_within_grace_warns_not_fails` (2 failed, 9 passed).
- Local full pytest suite + GitHub Actions CI green on PR before merge.
- Deployed via `scripts/vps/tag-rollback.sh`, `scripts/vps/sync-tooling.sh`, `scripts/vps/deploy-api.sh`.
- Verified live on `152.42.239.240`: `/healthz` OK, `social` reachable from `api`, `healthcheck.py --no-alert` reports `fail=0`, `scripts/seo-gate.sh` prints `GATE RESULT: PASS`, and `scripts/vps/verify-deploy.sh` exits `0`.
