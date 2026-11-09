#!/usr/bin/env bash
# Start only the isolated latest-source stack. Never alter production or OAuth staging.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TRENDI_WEBSITE="${TRENDI_WEBSITE:-$(dirname "$ROOT")/trendi-site-web}"
cd "$ROOT"
python3 scripts/local/configure.py init
COMPOSE=(docker compose --env-file /dev/null -f scripts/local/compose.yml)
docker info >/dev/null
# Reusing this dependency image is safe only while its requirements are identical.
EXPECTED="$(shasum -a 256 api/requirements.txt | awk '{print $1}')"
ACTUAL="$(docker run --rm --network none --entrypoint sha256sum concierge-api:oauth-staging-20261108 /srv/requirements.txt | awk '{print $1}')"
if [[ "$EXPECTED" != "$ACTUAL" ]]; then
  echo 'Dependency image is stale; refusing to build with different requirements.' >&2
  exit 1
fi
CARGO_BUILD_JOBS=1 nice -n 15 /Users/jo/.cargo/bin/cargo build --manifest-path concierge-stack/social-service/Cargo.toml --locked -j 1
python3 scripts/local/configure.py social
"${COMPOSE[@]}" build api
python3 scripts/local/verify-image.py
"${COMPOSE[@]}" up -d --wait db api tools
"${COMPOSE[@]}" exec -T api python - < scripts/local/bootstrap.py > .private/local-stack/runtime.pending.json
mv .private/local-stack/runtime.pending.json .private/local-stack/runtime.json
python3 scripts/local/configure.py render
"${COMPOSE[@]}" up -d --wait web
"${COMPOSE[@]}" exec -T web nginx -t
"${COMPOSE[@]}" exec -T web nginx -s reload
echo 'Trendi is running: http://127.0.0.1:8793/'
echo 'Admin: http://127.0.0.1:8793/admin-ui'
echo 'Admin key stays in .private/local-stack/admin-token.txt (never share it).'
