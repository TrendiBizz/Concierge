#!/usr/bin/env bash
# Re-crawl the website of named tenants (admin API POST /admin/tenants/<slug>/crawl) and verify the result.
# Crawl REPLACES all crawled chunks of the tenant (manual: chunks survive). Dry run by default: prints current
# state only. --apply starts the crawl, waits for it, then checks the chunks.
#
# Usage:  KEY=./Concierge ./scripts/vps/recrawl-tenants.sh [--apply] [--url-prefix URL] slug [slug...]
#   --url-prefix   URL prefix that must have chunks afterwards (default https://trendibizz.com/ai-office-builders)
# Verify per tenant: chunks for the prefix > 0, none match ifc|dwg|design upload, embedding dim of new rows.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
APPLY=0; PREFIX="https://trendibizz.com/ai-office-builders"; SLUGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --url-prefix) PREFIX="$2"; shift ;;
    *) SLUGS+=("$1") ;;
  esac; shift
done
[ ${#SLUGS[@]} -gt 0 ] || { echo "usage: $0 [--apply] [--url-prefix URL] slug..." >&2; exit 2; }
for s in "${SLUGS[@]}"; do [[ "$s" =~ ^[a-z0-9-]+$ ]] || { echo "bad slug: $s" >&2; exit 2; }; done
[[ "$PREFIX" =~ ^https?://[A-Za-z0-9./_-]+$ ]] || { echo "bad prefix" >&2; exit 2; }
ssh_() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "$@"; }
psql_() { ssh_ "podman exec -i trendi-postgres-1 psql -U postgres -d concierge -tA -F ' | '"; }

state() {
  local s="$1"
  psql_ <<SQL
SELECT '$s total chunks / urls: '||count(*)||' / '||count(DISTINCT c.url)
  FROM chunks c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='$s';
SELECT '$s prefix chunks: '||count(*) FROM chunks c JOIN tenants t ON t.id=c.tenant_id
  WHERE t.slug='$s' AND c.url LIKE '$PREFIX%';
SELECT '$s cad-term chunks: '||count(*) FROM chunks c JOIN tenants t ON t.id=c.tenant_id
  WHERE t.slug='$s' AND (c.content||c.title) ~* '(\mifc\M|\mdwg\M|design.?upload)';
SELECT '$s embedding dims: '||coalesce(string_agg(DISTINCT vector_dims(c.embedding)::text, ','),'none')
  FROM chunks c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='$s';
SQL
}

echo "== before =="; for s in "${SLUGS[@]}"; do state "$s"; done
if [ "$APPLY" -ne 1 ]; then echo "(dry run; pass --apply to crawl)"; exit 0; fi

for s in "${SLUGS[@]}"; do
  echo "== crawl $s =="
  ssh_ "ADMIN=\$(grep -m1 '^ADMIN_TOKEN=' /opt/trendi/shared/api.env | cut -d= -f2-); \
    curl -fsS -m 30 -X POST -H \"X-Admin-Token: \$ADMIN\" -H 'content-type: application/json' \
    -d '{\"max_pages\":80}' http://127.0.0.1:8000/admin/tenants/$s/crawl"; echo
done
echo "waiting for crawls (up to 6 min)..."
for _ in $(seq 1 36); do
  sleep 10
  ok=1
  for s in "${SLUGS[@]}"; do
    n=$(psql_ <<<"SELECT count(*) FROM chunks c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='$s' AND c.url LIKE '$PREFIX%';")
    [ "${n:-0}" -gt 0 ] || ok=0
  done
  [ "$ok" -eq 1 ] && break
done
sleep 15  # let the transaction and any remaining pages settle
echo "== after =="; for s in "${SLUGS[@]}"; do state "$s"; done
