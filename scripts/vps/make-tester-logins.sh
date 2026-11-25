#!/usr/bin/env bash
# Create empty throwaway tenants and mint one single-use owner sign-in link each (admin API).
# No email is sent (send_email=false); links expire in 24 hours and work once.
#
# Usage:  KEY=./Concierge ./scripts/vps/make-tester-logins.sh [--delete] slug [slug...]
#   default   create each tenant if missing (empty: no knowledge, no notify email), print a fresh link
#   --delete  delete the named tenants (cleanup of scratch tenants)
# Slugs must match ^[a-z0-9-]+$. Link secret is printed on purpose: hand it to the tester.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
MODE=create; SLUGS=()
for a in "$@"; do
  case "$a" in --delete) MODE=delete ;; *) SLUGS+=("$a") ;; esac
done
[ ${#SLUGS[@]} -gt 0 ] || { echo "usage: $0 [--delete] slug..." >&2; exit 2; }
for s in "${SLUGS[@]}"; do [[ "$s" =~ ^[a-z0-9-]+$ ]] || { echo "bad slug: $s" >&2; exit 2; }; done
ssh_() { ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "$@"; }
# Token stays on the box; only the API response is returned.
api() { # method path [json]
  ssh_ "ADMIN=\$(grep -m1 '^ADMIN_TOKEN=' /opt/trendi/shared/api.env | cut -d= -f2-); \
    curl -sS -m 30 -X $1 -H \"X-Admin-Token: \$ADMIN\" -H 'content-type: application/json' \
    ${3:+-d '$3'} -w '\n%{http_code}' http://127.0.0.1:8000$2"
}

for s in "${SLUGS[@]}"; do
  if [ "$MODE" = delete ]; then
    echo "== delete $s =="; api DELETE "/admin/tenants/$s" | tail -2; continue
  fi
  echo "== $s =="
  out=$(api GET "/admin/tenants/$s"); code=${out##*$'\n'}
  if [ "$code" = 404 ]; then
    n=${s##*-}
    out=$(api POST /admin/tenants "{\"name\":\"Tester $n\",\"slug\":\"$s\"}"); code=${out##*$'\n'}
    [ "$code" = 200 ] || { echo "create failed ($code): ${out%$'\n'*}" >&2; exit 1; }
    echo "created"
  else
    echo "exists (http $code); minting a fresh link only"
  fi
  out=$(api POST "/admin/tenants/$s/owner-invitations" "{\"email\":\"$s@trendibizz.com\",\"role\":\"owner\",\"send_email\":false}")
  code=${out##*$'\n'}; body=${out%$'\n'*}
  [ "$code" = 201 ] || { echo "invite failed ($code): $body" >&2; exit 1; }
  echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("link:", d["invitation_url"]); print("expires_in_hours:", d["expires_in_hours"], "emailed:", d["emailed"])'
done
