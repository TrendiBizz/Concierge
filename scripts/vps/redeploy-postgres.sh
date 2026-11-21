#!/usr/bin/env bash
# Recreate the Postgres container from the synced compose.yml and verify its memory limit
# and active PostgreSQL memory settings.
#
# Run `sync-tooling.sh` first so the updated compose.yml is on the box.
# Usage:  KEY=<deploy key> ./scripts/vps/redeploy-postgres.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
PRODUCT="$RELEASE/product"

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "set -euo pipefail
cd '$PRODUCT/scripts/vps'
COMPOSE=(podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public)

echo '==> recreating postgres from compose.yml'
\"\${COMPOSE[@]}\" up -d --force-recreate --no-deps postgres

TEMP_PG=\"\$(podman ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]+_trendi-postgres-1\$' | head -1 || true)\"
if [ -n \"\$TEMP_PG\" ]; then
  echo \"    normalising container name \$TEMP_PG -> trendi-postgres-1\"
  podman rename \"\$TEMP_PG\" trendi-postgres-1
fi

echo '==> waiting for postgres readiness'
PG_READY=0
for _ in \$(seq 1 30); do
  if podman exec trendi-postgres-1 pg_isready -U postgres -d concierge >/dev/null 2>&1; then
    PG_READY=1
    break
  fi
  sleep 2
done
if [ \"\$PG_READY\" -ne 1 ]; then
  echo 'postgres did not become ready within 60s' >&2
  exit 1
fi

echo '==> container memory limit and active PostgreSQL settings'
podman inspect -f 'Memory={{.HostConfig.Memory}} ShmSize={{.HostConfig.ShmSize}}' trendi-postgres-1
podman exec trendi-postgres-1 psql -U postgres -d concierge -Atc \"
  SELECT name || '=' || setting || COALESCE(' ' || NULLIF(unit, ''), '')
  FROM pg_settings
  WHERE name IN ('shared_buffers', 'effective_cache_size', 'work_mem', 'maintenance_work_mem', 'wal_buffers', 'max_connections')
  ORDER BY name;
\"
echo '==> postgres ready'
"
