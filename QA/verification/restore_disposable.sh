#!/usr/bin/env bash
# Self-contained canary dump/restore using a throwaway Docker pgvector database.
# Does not connect to or modify an existing database or container.
set -euo pipefail
container="cc-restore-proof-$$"
archive="$(mktemp -t concierge-restore.XXXXXX)"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -f "$archive"
}
trap cleanup EXIT
docker run -d --rm --name "$container" -e POSTGRES_PASSWORD=test pgvector/pgvector:pg16 >/dev/null
ready=0
for i in {1..30}; do
  if docker exec "$container" psql -U postgres -d postgres -At -c "SELECT 1" 2>/dev/null | grep -qx 1; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo "Disposable postgres did not start"; exit 1; }
docker exec "$container" psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE TABLE public.restore_canary(value text PRIMARY KEY)" >/dev/null
docker exec "$container" psql -U postgres -v ON_ERROR_STOP=1 -c "INSERT INTO public.restore_canary VALUES ('verified')" >/dev/null
docker exec "$container" pg_dump -U postgres --format=custom --table=public.restore_canary postgres > "$archive"
docker exec "$container" psql -U postgres -v ON_ERROR_STOP=1 -c "DROP TABLE public.restore_canary" >/dev/null
docker exec -i "$container" pg_restore -U postgres --dbname=postgres --exit-on-error < "$archive"
actual="$(docker exec "$container" psql -U postgres -At -c 'SELECT value FROM public.restore_canary')"
[[ "$actual" == "verified" ]] || { echo "Restore verification failed"; exit 1; }
echo 'PASS: isolated canary restored from pg_dump archive; disposable DB removed on exit'
