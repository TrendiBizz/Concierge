# Postgres tuning, taking the multicore-server-challenge's method rather than its numbers

Source read: [arjaythedev/multicore-server-challenge](https://github.com/arjaythedev/multicore-server-challenge) —
`box/pg-conf.sh` writes pgtune's "Web application" profile for an 8-thread / 16 GiB box with 100
connections, and the leaderboard is won by servers that avoid N+1 queries and pool connections,
not by exotic Postgres settings. The transferable part is the *method*: size the memory settings
from the box, and get the planner's storage assumptions right.

## Their box vs ours

| | Challenge box | Our VPS |
|---|---|---|
| CPU | 8 vCPU | **2** |
| RAM | 16 GiB, Postgres owns it | **8 GiB, shared with API, website, Asterisk, Chatwoot, Twenty** |
| Postgres | 18 | **16** (pgvector image) |
| Database | ~10 GB seed | **20 MB** |
| Connections | 100 | 40 |

Their formulas assume Postgres owns the machine (`shared_buffers = RAM/4 = 4 GB`). Applying that
here would take 2 GB from a box running six other containers for a 20 MB database. So the memory
values are capped deliberately, and only the settings that change *planner and observability
behaviour* are taken at full strength.

## What changed (persisted in `scripts/vps/compose.yml`, not just `ALTER SYSTEM`)

Before: `[postgres, -c, max_connections=40, -c, shared_buffers=64MB]` — everything else stock.

| Setting | Before | After | Why |
|---|---|---|---|
| shared_buffers | 64 MB | 512 MB | headroom without starving the other containers |
| effective_cache_size | 4 GB | 2 GB | honest estimate on a shared 8 GiB box |
| work_mem | 4 MB | 8 MB | fewer spill files on sorts/aggregates as tenants grow |
| maintenance_work_mem | 64 MB | 128 MB | faster vacuum/index builds |
| random_page_cost | 4 | **1.1** | SSD: 4 makes the planner over-prefer seq scans |
| effective_io_concurrency | 1 | **200** | same reason — no seek penalty to model |
| wal_buffers | 256 kB | 16 MB | write burst absorption |
| min/max_wal_size | 80 MB / 1 GB | 512 MB / 2 GB | fewer checkpoints |
| max_worker_processes / parallel workers | 8 / 8 | 2 / 2 (1 per gather) | 2 cores; the old values let Postgres spawn more workers than cores |
| **shared_preload_libraries** | *(empty)* | **pg_stat_statements** | we had no per-query cost visibility at all |
| pg_stat_statements.max / track | — | 2000 / all | same |

Applied by recreating the container (`docker compose -f scripts/vps/compose.yml --env-file
/opt/trendi/shared/compose.env up -d postgres`), then `CREATE EXTENSION pg_stat_statements`.

## Proof

```
before:  4867.8 tps, latency average 0.822 ms   (pgbench, 4 clients, 15 s, hot inbox query)
after:   4635.1 tps, 0.863 ms
after:   4322.3 tps, 0.925 ms   (third run, warm)
```
**No improvement — and that is the correct result to report.** The database is 20 MB and 100%
cached, the query plans are byte-identical at `random_page_cost` 1.1 and 4 (`EXPLAIN` cost 3.40
both ways), and the run-to-run spread on this shared box is larger than any difference the settings
could make. The values are still right to have, because they are what the box will need as tenants
grow past the memory size, but nobody should claim a speed-up from them.

## What the new visibility immediately showed

```
total_ms | calls  | mean_ms | query
 7716.3  | 134293 |  0.057  | conversations list (inbox)
 5098.5  | 134293 |  0.038  | messages for the latest conversation
    5.0  |     48 |  0.103  | device_sms_jobs claim
```
The hot paths cost 57 µs and 38 µs. Index hit ratio 99.92%, table hit ratio 100%. There is no
missing index to add on the inbox path.

One thing that *looks* like a problem and is not: `outbox` does 31,867 seq scans against 53,319
index scans. The table is 378 rows / one page — a seq scan is the correct plan there, and forcing
an index would make the outbox worker (polled every few seconds) slower. Left alone, deliberately.
