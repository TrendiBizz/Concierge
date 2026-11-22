#!/usr/bin/env bash
# Redeploy the API — and anything that shares its network namespace.
#
# social uses `network_mode: service:api`, so it lives inside the api container's namespace.
# Recreating api on its own strands the old social process on a dead namespace: the api then
# answers "Social service unavailable" for every provider while `podman ps` still shows social up.
# That happened on 2026-11-14 and looked like a Social bug from the browser.
#
# Under Podman (2026-11-17) one `up --force-recreate api social` fails: the daemon refuses to
# remove api while social still exists, and the failed pass left api down. Remove social first,
# recreate api, then recreate social. Podman's compose path can also name the recreated container
# "<oldid>_trendi-api-1" (or "<oldid>_trendi-social-1"); normalise that, because every other script
# looks them up as trendi-api-1 / trendi-social-1.
#
# Usage:
#   redeploy-api.sh              # build api image, recreate api + social, verify both
#   redeploy-api.sh --no-build   # recreate api + social from current image (e.g. after api.env change)
set -euo pipefail

BUILD=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-build) BUILD=0 ;;
    *) echo "usage: $0 [--no-build]" >&2; exit 2 ;;
  esac
  shift
done

REL="${REL:-/opt/trendi/releases/20261108-vps/product}"
mkdir -p /var/lock
exec 9>/var/lock/trendi-redeploy-api.lock
if ! flock -w 300 9; then
  echo "Refusing: another redeploy-api.sh holds /var/lock/trendi-redeploy-api.lock" >&2
  exit 1
fi
cd "$REL/scripts/vps"
COMPOSE=(podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public)

if [ "$BUILD" -eq 1 ]; then
  echo "==> building api"
  "${COMPOSE[@]}" build api
fi

echo "==> removing social (shares api's namespace), then recreating api"
"${COMPOSE[@]}" rm -sf social
for stray in $(podman ps -a --format '{{.Names}}' | grep -E '^([0-9a-f]+_)?trendi-social-1$' || true); do
  podman rm -f "$stray" >/dev/null 2>&1 || true
done

"${COMPOSE[@]}" up -d --force-recreate --no-deps api
TEMP_API="$(podman ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]+_trendi-api-1$' | head -1 || true)"
if [ -n "$TEMP_API" ]; then
  echo "    normalising container name $TEMP_API -> trendi-api-1"
  podman rename "$TEMP_API" trendi-api-1
fi

echo "==> recreating social in api's namespace"
"${COMPOSE[@]}" up -d --force-recreate --no-deps social
TEMP_SOCIAL="$(podman ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]+_trendi-social-1$' | head -1 || true)"
if [ -n "$TEMP_SOCIAL" ]; then
  echo "    normalising container name $TEMP_SOCIAL -> trendi-social-1"
  podman rename "$TEMP_SOCIAL" trendi-social-1
fi

echo "==> waiting for the api"
API_READY=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  sleep 2
done
if [ "$API_READY" -ne 1 ]; then
  echo "api did not answer /healthz within 60s" >&2
  exit 1
fi

echo "==> verifying social shares api's network namespace"
API_ID="$(podman inspect -f '{{.Id}}' trendi-api-1)"
SOCIAL_NET="$(podman inspect -f '{{.HostConfig.NetworkMode}}' trendi-social-1)"
if [ "$SOCIAL_NET" != "container:$API_ID" ]; then
  echo "social NetworkMode is '$SOCIAL_NET', expected 'container:$API_ID'" >&2
  exit 1
fi

echo "==> checking social answers from inside the api container"
SOCIAL_OK=0
for _ in $(seq 1 10); do
  if podman exec trendi-api-1 python3 -c "
import os, urllib.request, urllib.error
base = os.environ.get('SOCIAL_SERVICE_URL', 'http://127.0.0.1:4390').rstrip('/')
try:
    urllib.request.urlopen(base + '/v1/customers', timeout=5)
except urllib.error.HTTPError:
    pass  # answering at all is what matters
print('social reachable')
" 2>/dev/null; then
    SOCIAL_OK=1
    break
  fi
  sleep 2
done
if [ "$SOCIAL_OK" -ne 1 ]; then
  echo "social NOT reachable from the api — recreate social again" >&2
  exit 1
fi
echo "==> done"
