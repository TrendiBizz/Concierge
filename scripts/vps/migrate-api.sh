#!/usr/bin/env bash
# Run `alembic upgrade head` inside the running API container. Prints the revision before and after.
#
# Usage:  KEY=<deploy key> ./scripts/vps/migrate-api.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" 'set -e
  run() { podman exec trendi-api-1 sh -c "cd /srv && alembic $*" 2>&1 | grep -v "^INFO  \[alembic.runtime.migration\] Will assume"; }
  echo "before:"; run current
  run upgrade head
  echo "after:"; run current'
