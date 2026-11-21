#!/usr/bin/env bash
# Dump the hermes_* tables (data + structure) on the box, then copy the dump to this Mac.
# Run BEFORE the 0002 migration drops them.
#
# Usage:  KEY=<deploy key> ./scripts/vps/hermes-db-backup.sh [local-dir]   (default ~/Reports/remove-leftovers)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
OUT="${1:-$HOME/Reports/remove-leftovers}"
FILE="hermes-tables-$(date +%Y%m%d).sql"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST")
mkdir -p "$OUT"
"${SSH[@]}" "set -e; umask 077; mkdir -p /opt/trendi/backups
  podman exec trendi-postgres-1 pg_dump -U postgres -d concierge -t 'hermes_*' --no-owner --no-acl > /opt/trendi/backups/$FILE
  [ -s /opt/trendi/backups/$FILE ] || { echo 'dump is empty' >&2; exit 1; }
  grep -c 'CREATE TABLE' /opt/trendi/backups/$FILE | sed 's/^/tables in dump: /'"
scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST:/opt/trendi/backups/$FILE" "$OUT/$FILE"
chmod 600 "$OUT/$FILE"
echo "box: /opt/trendi/backups/$FILE   mac: $OUT/$FILE ($(wc -c < "$OUT/$FILE") bytes)"
