#!/usr/bin/env bash
# Start (creating once) the throwaway test Postgres the API suite needs, on 127.0.0.1:55433.
# Needs: brew install postgresql@17 pgvector. Data lives outside the repo.
set -euo pipefail
B=/opt/homebrew/opt/postgresql@17/bin
D="${PGTEST_DIR:-$HOME/work-staging/pgdata-concierge-test}"
if [ ! -d "$D" ]; then
  pw=$(mktemp); echo pw > "$pw"
  "$B/initdb" -D "$D" -U postgres --auth=md5 --pwfile="$pw" >/dev/null; rm -f "$pw"
fi
"$B/pg_ctl" -D "$D" status >/dev/null 2>&1 || \
  "$B/pg_ctl" -D "$D" -o "-p 55433 -h 127.0.0.1 -c fsync=off" -l "$D/log.txt" -w start
PGPASSWORD=pw "$B/psql" -h 127.0.0.1 -p 55433 -U postgres -qc "CREATE EXTENSION IF NOT EXISTS vector"
echo "test db ready: postgresql://postgres:pw@127.0.0.1:55433/postgres"
