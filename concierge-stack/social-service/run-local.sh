#!/usr/bin/env bash
# Local-only Concierge Social service. Network publishing is disabled by default.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/data/social.env"
mkdir -p "$DIR/data"
chmod 700 "$DIR/data"
if [[ ! -f "$ENV_FILE" ]]; then
  umask 077
  cat > "$ENV_FILE" <<ENVIRONMENT
SOCIAL_VAULT_KEY=$(openssl rand -base64 32)
SOCIAL_CONCIERGE_KEY=$(openssl rand -hex 32)
SOCIAL_AGENT_KEY=$(openssl rand -hex 32)
SOCIAL_DB=$DIR/data/social.db
SOCIAL_BIND=127.0.0.1:4390
SOCIAL_ENABLE_PUBLISH=false
ENVIRONMENT
  chmod 600 "$ENV_FILE"
  echo "Generated local-only private social configuration."
fi
if [[ "$(stat -f '%Lp' "$ENV_FILE")" != "600" ]]; then
  echo "Social configuration must have permissions 600" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
if [[ "$SOCIAL_ENABLE_PUBLISH" == "true" ]]; then
  echo "Live social publishing is enabled in the configuration. Explicit authorization required." >&2
  exit 1
fi
cd "$DIR"
exec cargo run --locked --release
