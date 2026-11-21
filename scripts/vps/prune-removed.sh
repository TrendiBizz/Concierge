#!/usr/bin/env bash
# Move files that were deleted from the repo out of the release tree on the box.
#
# Why this exists: the deploy rsyncs never delete, so a file removed from the repo stays on the box,
# keeps showing up as drift in verify-deploy.sh, and (for api/app) is still baked into the image.
# Nothing is deleted: each listed path is MOVED into $RELEASE/removed/<date>/ so it can be put back.
#
# Usage:  KEY=./Concierge ./scripts/vps/prune-removed.sh      (called by sync-tooling.sh and deploy-api.sh)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
LIST="$REPO_ROOT/scripts/vps/removed-paths.txt"
[ -f "$LIST" ] || { echo "no $LIST" >&2; exit 1; }

PATHS="$(grep -vE '^\s*(#|$)' "$LIST")"
# shellcheck disable=SC2029
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "set -e; cd '$RELEASE/product'; dest='$RELEASE/removed/'\$(date +%Y%m%d); n=0
   while IFS= read -r p; do
     [ -n \"\$p\" ] || continue
     if [ -e \"\$p\" ]; then mkdir -p \"\$dest/\$(dirname \"\$p\")\"; mv \"\$p\" \"\$dest/\$p\"; echo \"  moved \$p\"; n=\$((n+1)); fi
   done <<'LIST'
$PATHS
LIST
   echo \"prune-removed: \$n path(s) moved to \$dest\""
