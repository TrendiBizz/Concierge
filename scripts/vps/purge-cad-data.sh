#!/usr/bin/env bash
# Purge leftover data of the removed 3D / Designs / IFC feature (Jo, 2026-11-25: "remove all data pertaining
# to CAD or drawings"). Dry run by default: prints what would go. --apply deletes.
#   1. knowledge chunks of the old trendibizz.com/ai-office-builders crawl that still advertise IFC / DWG /
#      design upload (tenants trendi-support, trendi-oauth-staging; the live page no longer says it)
#   2. cached UI translation "Designs and CAD"
#   3. the archived uploads folder /opt/trendi/shared/removed/designs-*
# Customer messages, outbox mail and the Pukeko cladding business content are NOT touched.
#
# Usage:  KEY=./Concierge ./scripts/vps/purge-cad-data.sh [--apply]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
PAT='(\mifc\M|\mdwg\M|design.?upload|\mcad\M)'
ssh_() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "$@"; }
psql_() { ssh_ "podman exec -i trendi-postgres-1 psql -U postgres -d concierge -tA"; }

echo "== chunks to delete (url, count) =="
psql_ <<SQL
SELECT t.slug, c.url, count(*) FROM chunks c JOIN tenants t ON t.id=c.tenant_id
WHERE c.url LIKE 'https://trendibizz.com/ai-office-builders%' AND t.slug IN ('trendi-support','trendi-oauth-staging')
GROUP BY 1,2;
SELECT 'ui_translation_cache rows: '||count(*) FROM ui_translation_cache WHERE source ~* '(\mcad\M|designs and cad)';
SQL
echo "== archive folder =="
ssh_ 'ls -la /opt/trendi/shared/removed/ 2>/dev/null; find /opt/trendi/shared/removed -maxdepth 3 -name "designs-*" -exec find {} -type f \;'
if [ "$APPLY" -ne 1 ]; then echo "(dry run; pass --apply to delete)"; exit 0; fi

psql_ <<SQL
BEGIN;
DELETE FROM chunks WHERE url LIKE 'https://trendibizz.com/ai-office-builders%'
  AND tenant_id IN (SELECT id FROM tenants WHERE slug IN ('trendi-support','trendi-oauth-staging'));
DELETE FROM ui_translation_cache WHERE source ~* '(\mcad\M|designs and cad)';
COMMIT;
SQL
ssh_ 'rm -rf /opt/trendi/shared/removed/designs-*; ls /opt/trendi/shared/removed/ 2>/dev/null; echo archive removed'
echo "== re-scan =="
KEY="$KEY" "$REPO_ROOT/scripts/vps/scan-cad-data.sh" | sed -n '1,/DB tables/p' | grep -E 'chunks\.|ui_translation' || echo "no chunks/ui_translation matches"
