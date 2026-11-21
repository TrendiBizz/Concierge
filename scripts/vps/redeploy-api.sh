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
# "<oldid>_trendi-api-1"; normalise that, because every other script looks it up as trendi-api-1.
set -euo pipefail

REL="${REL:-/opt/trendi/releases/20261108-vps/product}"
cd "$REL/scripts/vps"
COMPOSE=(podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public)

echo "==> building api"
"${COMPOSE[@]}" build api

echo "==> removing social (shares api's namespace), then recreating api"
"${COMPOSE[@]}" rm -sf social
"${COMPOSE[@]}" up -d --no-deps api
TEMP_API="$(podman ps --format '{{.Names}}' | grep -E '^[0-9a-f]+_trendi-api-1$' | head -1 || true)"
if [ -n "$TEMP_API" ]; then
  echo "    normalising container name $TEMP_API -> trendi-api-1"
  podman rename "$TEMP_API" trendi-api-1
fi

echo "==> recreating social in api's namespace"
"${COMPOSE[@]}" up -d --no-deps social

echo "==> waiting for the api"
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
  sleep 2
done

echo "==> checking social answers from inside the api container"
podman exec trendi-api-1 python3 -c "
import os, urllib.request
base = os.environ.get('SOCIAL_SERVICE_URL', 'http://127.0.0.1:4390').rstrip('/')
try:
    urllib.request.urlopen(base + '/v1/customers', timeout=5)
except urllib.error.HTTPError:
    pass  # answering at all is what matters
print('social reachable')
" || { echo "social NOT reachable from the api — recreate social again" >&2; exit 1; }
echo "==> done"
