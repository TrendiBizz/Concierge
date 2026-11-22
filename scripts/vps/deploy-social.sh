#!/usr/bin/env bash
# Deploy the Rust social service (concierge-stack/social-service) to the VPS.
#
# Syncs the Rust source + Containerfile.social, rebuilds trendi-concierge-social:vps,
# recreates the social container inside api's network namespace under the shared
# redeploy lock, verifies social is reachable from api, and runs verify-deploy.sh.
#
# usage: KEY=./Concierge ./scripts/vps/deploy-social.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
PRODUCT="$RELEASE/product"

SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST")
RSSH=(rsync -a --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r --delay-updates
      -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY")

[ -d "$REPO_ROOT/concierge-stack/social-service/src" ] || { echo "no social-service in $REPO_ROOT" >&2; exit 1; }

if [ "${ALLOW_DIRTY:-0}" != "1" ] && git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  dirty="$(env -u GIT_CONFIG_COUNT git -C "$REPO_ROOT" status --porcelain -- concierge-stack/social-service scripts/vps/Containerfile.social scripts/vps/deploy-social.sh)"
  if [ -n "$dirty" ]; then
    echo "Refusing to deploy uncommitted changes (commit first, or set ALLOW_DIRTY=1):" >&2
    echo "$dirty" >&2
    exit 1
  fi
fi

echo "==> syncing concierge-stack/social-service to $HOST:$PRODUCT/concierge-stack/social-service"
"${SSH[@]}" "mkdir -p '$PRODUCT/concierge-stack/social-service/src'"
"${RSSH[@]}" --exclude 'target/' "$REPO_ROOT/concierge-stack/social-service/" "$HOST:$PRODUCT/concierge-stack/social-service/"
"${RSSH[@]}" "$REPO_ROOT/scripts/vps/Containerfile.social" "$REPO_ROOT/scripts/vps/Containerfile.social.dockerignore" "$HOST:$PRODUCT/scripts/vps/"

echo "==> rebuilding and recreating social inside api's network namespace"
"${SSH[@]}" "set -euo pipefail
mkdir -p /var/lock
exec 9>/var/lock/trendi-redeploy-api.lock
flock -w 300 9
cd '$PRODUCT/scripts/vps'
COMPOSE=(podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public)
\"\${COMPOSE[@]}\" build social
\"\${COMPOSE[@]}\" rm -sf social
for stray in \$(podman ps -a --format '{{.Names}}' | grep -E '^([0-9a-f]+_)?trendi-social-1$' || true); do
  podman rm -f \"\$stray\" >/dev/null 2>&1 || true
done
\"\${COMPOSE[@]}\" up -d --force-recreate --no-deps social
TEMP_SOCIAL=\"\$(podman ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]+_trendi-social-1$' | head -1 || true)\"
if [ -n \"\$TEMP_SOCIAL\" ]; then
  podman rename \"\$TEMP_SOCIAL\" trendi-social-1
fi
for _ in \$(seq 1 10); do
  if podman exec trendi-api-1 python3 -c \"
import os, urllib.request, urllib.error
base = os.environ.get('SOCIAL_SERVICE_URL', 'http://127.0.0.1:4390').rstrip('/')
try:
    urllib.request.urlopen(base + '/v1/customers', timeout=5)
except urllib.error.HTTPError:
    pass
print('social reachable')
\" 2>/dev/null; then
    exit 0
  fi
  sleep 2
done
echo 'social NOT reachable from api' >&2
exit 1"

echo "==> verifying repo and box agree"
KEY="$KEY" VPS_HOST="$HOST" VPS_RELEASE="$RELEASE" "$REPO_ROOT/scripts/vps/verify-deploy.sh"
