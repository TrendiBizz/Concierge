# C2 — Postgres Memory Budget, Lifespan Shutdown Leaks & Uptime Probe Cleanup (2026-11-21)

Source of truth: `~/Reports/neon-improvements/report.md` (Section 4, Tier 0 — C2).

## Cause

Three reliability defects were identified in the audit:
1. **Postgres memory contradiction (`scripts/vps/compose.yml`):** The `postgres` service was configured with `shared_buffers=512MB`, `effective_cache_size=2GB`, `work_mem=8MB`, `maintenance_work_mem=128MB`, and `max_connections=40` inside a container capped at `mem_limit: 384m` (with no explicit `shm_size`), creating an OOM-kill hazard as soon as the active working set, `pgvector` HNSW indexes, or `voice_recordings` blobs grew beyond ~20 MB.
2. **Unawaited background tasks on API shutdown (`api/app/main.py`):** `lifespan()` started `missed_worker` (`missed_calls.run_forever`) and `insights_worker` (`call_insights.run_forever`) when `outbox_enabled` was true, but never awaited either task on shutdown before calling `await db.close()`. In addition, `yield` was not guarded by `try ... finally`, and awaiting workers sequentially meant an exception in one worker could skip awaiting the rest.
3. **Dead uptime probe (`.github/workflows/uptime.yml`):** The outside-in uptime workflow still probed `https://crm.trendibizz.com/` and checked its TLS certificate after Twenty CRM was retired on 2026-11-17.

## Fix

1. **Bounded Postgres memory settings (`scripts/vps/compose.yml`):** Raised `postgres` container `mem_limit` to `1024m` and added `shm_size: 256m`, while setting `shared_buffers=256MB` (25% of container limit), `effective_cache_size=768MB` (75% of container limit), and `work_mem=4MB` (`256 + 128 + 16 + 40 * 4 = 560 MB < 1024 m`). Added repo helper script `scripts/vps/redeploy-postgres.sh` so the updated `postgres` service configuration is applied and verified cleanly via repo tooling.
2. **Leak-free lifespan shutdown (`api/app/main.py`):** Collected every background worker (including `missed_worker` and `insights_worker`) into a single `workers` list inside `lifespan()`, wrapped `yield` in `try ... finally`, set `stop`, awaited all workers with `asyncio.gather(*workers, return_exceptions=True)` (logging any unexpected worker error), and only then called `await db.close()`.
3. **Removed retired CRM probes (`.github/workflows/uptime.yml`):** Removed `https://crm.trendibizz.com/` from the HTTP probe list (along with its redirect exception) and removed `crm.trendibizz.com` from the TLS expiry loop so the workflow matches `scripts/vps/healthcheck.py`.

## Proof

- Added `api/tests/test_c2_reliability.py` (10 test cases):
  - Verifies `scripts/vps/compose.yml` Postgres memory invariants (`shared_buffers <= 35%` of `mem_limit`, `effective_cache_size <= mem_limit`, `shm_size >= 128m`, combined worst-case memory budget `< mem_limit`).
  - Parameterized shutdown test across all 7 background workers (`outbox`, `sla`, `sales`, `missed_calls`, `call_insights`, `email_secretary`, `calendar`) proving each worker is awaited before `db.close()` runs and zero tasks leak after `lifespan()` exits.
  - Error-resilience test proving remaining workers (`missed_calls`, `call_insights`) and `db.close()` still complete cleanly when another worker raises on shutdown.
  - Verifies `crm.trendibizz.com` is absent from `.github/workflows/uptime.yml` while active endpoints remain covered.
- Mutation checks confirmed red -> green for all three fixes:
  - Spawning `missed_worker` without awaiting it: failed (`1 failed, 9 passed`).
  - Restoring `shared_buffers=512MB` with `mem_limit: 384m`: failed (`1 failed, 9 passed`).
  - Restoring `crm.trendibizz.com` to `uptime.yml`: failed (`1 failed, 9 passed`).
  - Restored code: passed (`10 passed`).
- Full local API test suite (`scripts/dev/test-db.sh` + pytest): `1610 passed, 42 skipped` (0 failed).
- Static checks (`python3 -m compileall -q api/app QA/verification`, `bash -n scripts/vps/redeploy-postgres.sh`, `git diff --check`): exit 0.
- Site SEO contract (`python3 scripts/seo/site_seo.py check`): `OK: 46 pages`.
