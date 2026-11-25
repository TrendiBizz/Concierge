#!/usr/bin/env bash
# READ-ONLY. Count rows in every text/json column of the concierge DB that mention CAD / drawings
# (cad, dwg, ifc, 3d, bonsai, drawing, cladding, floor plan, design upload, takeoff), and list files
# on the box that look like CAD/design data. Changes nothing. Prints column + count only, never row text.
#
# Usage:  KEY=./Concierge ./scripts/vps/scan-cad-data.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
PAT='(\mcad\M|\mdwg\M|\mifc\M|\m3d\M|bonsai|drawing|cladding|floor ?plan|design.?upload|takeoff|take-off)'
SQL="
SELECT table_name||'.'||column_name AS col,
       (xpath('/row/c/text()', query_to_xml(format(
         'SELECT count(*) AS c FROM %I.%I WHERE %I::text ~* %L', table_schema, table_name, column_name, '$PAT'),
         false, true, '')))[1]::text::int AS hits
FROM information_schema.columns
WHERE table_schema='public'
  AND data_type IN ('text','character varying','json','jsonb')
ORDER BY 2 DESC, 1;"
echo "== DB columns with matches (hits > 0) =="
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "podman exec -i trendi-postgres-1 psql -U postgres -d concierge -tA -F ' | '" <<<"$SQL" | awk -F' [|] ' '$2>0'
echo "== DB tables with design/cad/quote_profile names =="
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "podman exec -i trendi-postgres-1 psql -U postgres -d concierge -tA" <<<"SELECT table_name||'.'||column_name FROM information_schema.columns WHERE table_schema='public' AND column_name ~* '(design|cad|takeoff|ifc|dwg)' ORDER BY 1;"
echo "== box files (names only) =="
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "find /opt/trendi/shared -xdev \( -iname '*.ifc' -o -iname '*.dwg' -o -iname '*.dxf' -o -iname '*.stl' -o -iname '*.glb' -o -iname '*design*' \) -not -path '*/node_modules/*' 2>/dev/null | head -40"
