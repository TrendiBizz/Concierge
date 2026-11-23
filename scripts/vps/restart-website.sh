#!/usr/bin/env bash
# Restart ONLY the website container (no purge, no file sync) so it re-reads website.mjs and the worker.
#
# Why: website.mjs loads its code once at start. deploy-site.sh restarts the website but also syncs the site,
# purges the Cloudflare cache and pings IndexNow; when only website.mjs changed (2026-11-24: /api/* is no
# longer answered by the untracked worker file) none of that is wanted. Run sync-tooling.sh first, so the new
# website.mjs is on the box, then this. Nothing else restarts: no postgres, api, gateway or volumes.
#
# Usage:  KEY=./Concierge ./scripts/vps/restart-website.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
"${SSH[@]}" "$HOST" "cd '$RELEASE/product/scripts/vps' && podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public restart website >/dev/null"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -o /dev/null --max-time 15 "${SITE_URL:-https://trendibizz.com}/"; then
    echo "website restarted and answering"
    exit 0
  fi
done
echo "FAIL: the site did not answer after the website restart" >&2
exit 1
