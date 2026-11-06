# Verification scripts

These are the scripts used to test the Concierge API and dashboard. They are kept here so the checks can be re-run.

**They never touch the live system.** Each one starts its own throwaway Postgres container (port 55432) and, where it needs a running API, its own API on port 18080 or 18081. The benchmark uses a separate Docker network.

**Paths are hard-coded** for the layout used when they were written: the repository checked out at `~/work-staging/concierge-office`, helper files in `~/work-staging`, a Python virtualenv at `~/work-staging/venv-concierge`, and `puppeteer-core` installed under `~/concierge/vm/nav-test`. Edit the paths at the top of each script for another machine. `fastembed` has no build for very new Python versions, so the host-run scripts put a tiny stub for it on the path (`shims/fastembed.py`); the Docker-based benchmark uses the real model.

## Python integration checks (real code against a real database)

| Script | Covers | Checks |
|---|---|---|
| `score_integration.py` | lead scoring, owner alert text | 12 |
| `phase3_integration.py` | per-client scoring weights, response-time alerts | 21 |
| `campaign_integration.py` | reactivation campaign engine, consent, unsubscribe, kill switch | 24 |
| `campaign_routes_check.py` | campaign admin routes, unsubscribe page, consent tool | 19 |
| `office_integration.py` | to-dos, pipeline, weekly summary, calendar feed | 63 |

Start a database first: `docker run -d --rm --name cc-office-test -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 pgvector/pgvector:pg16`, wait a few seconds, then run a script. Use a fresh database for each script.

## Browser checks (real Chrome against the real dashboard)

| Script | Covers | Checks |
|---|---|---|
| `run_dashboard_test.sh` (+ `seed_dashboard.py`, `dashboard_test.cjs`) | needs-attention, leads, campaigns, setup, scoring editor | 29 |
| `run_office_test.sh` (+ `seed_office.py`, `office_dashboard_test.cjs`) | pipeline board, to-dos, overview, calendar link, weekly summary | 32 |

Each runner builds a fresh database, starts the API, seeds demo data, runs the browser test and cleans up.

## Benchmark (`bench/`)

`run_bench.sh` starts the production image (Python 3.12, one worker, real embedding model) on a throwaway database with an instant stand-in model, so only our own code is measured. `api_bench.py` measures latency and throughput from outside; `inside_bench.py` runs inside the container and times retrieval and phone-audio conversion. `run_bench_t1.sh` repeats it with the embedding model limited to one thread per call.
