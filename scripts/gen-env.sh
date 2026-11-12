#!/usr/bin/env bash
# Create .env from .env.example with random secrets filled in.
# Refuses to overwrite an existing .env.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists - not overwriting. Delete it first if you want a fresh one." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate secrets" >&2
  exit 1
fi

cp .env.example .env

fill() {
  local key="$1" bytes="$2" value
  value="$(openssl rand -hex "$bytes")"
  # Only fill if the value is currently empty.
  sed -i.bak -E "s|^${key}=$|${key}=${value}|" .env
}

fill POSTGRES_PASSWORD 24
fill ADMIN_TOKEN 24
fill CHATWOOT_SECRET_KEY_BASE 64
fill TWENTY_APP_SECRET 32
rm -f .env.bak

chmod 600 .env
echo "Created .env with random secrets."
echo "Now edit .env and set XAI_API_KEY (and DOMAIN / PUBLIC_BASE_URL for production)."
