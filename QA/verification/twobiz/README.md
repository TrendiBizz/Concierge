# Two-business end-to-end verification

Runs two fully configured businesses through the real application code against a **real Postgres**
with the **real schema**, and asserts the isolation the mandate requires: one customer contacting
both businesses produces two distinct cases, retried webhooks collapse, each owner is reached only
at their own destinations, an acknowledgement belongs to the enquirer of the right business,
quotations are visible to one business and not the other, availability is computed in each
business's own timezone, and readiness moves for one business without affecting the other.

## Why the launcher exists

An earlier version of this test set `os.environ["DATABASE_URL"]` inside the script. `app.config
.get_settings()` is decorated with `@lru_cache`, and that cache had already been filled by the
time the override ran, so the script silently wrote **two fake tenants into production** (repeated
runs and `tenants.create()`'s slug suffixing produced `harbour-dental` through `-5`). That was
cleaned up, and the details are recorded in `PORTAL_WORKFLOW_LIVE_VERIFICATION_2026-11-10.md`.

Two things now make that impossible:

1. `run_twobiz.sh` exports `DATABASE_URL` **before** Python starts, and refuses to continue unless
   settings report the throwaway database.
2. `twobiz_e2e.py` re-checks the same condition at import time and exits non-zero if the target is
   not `concierge_twobiz_verify`.

## Usage

```sh
# On the host, with the API image available:
docker exec trendi-postgres-1 psql -U postgres -c "CREATE DATABASE concierge_twobiz_verify;"
docker exec trendi-postgres-1 psql -U postgres -d concierge_twobiz_verify -c "CREATE EXTENSION IF NOT EXISTS vector;"
sed 's/__DIM__/384/g' api/app/schema.sql > /tmp/schema384.sql
docker exec -i trendi-postgres-1 psql -U postgres -d concierge_twobiz_verify -q -v ON_ERROR_STOP=1 < /tmp/schema384.sql

docker cp twobiz_e2e.py trendi-api-1:/tmp/
docker cp run_twobiz.sh trendi-api-1:/tmp/
docker exec -w /srv -e PYTHONPATH=/srv trendi-api-1 sh /tmp/run_twobiz.sh
```

Expected final line: `ALL TWO-BUSINESS END-TO-END CHECKS PASSED`.

Clean up with `DROP DATABASE concierge_twobiz_verify;` when finished.
