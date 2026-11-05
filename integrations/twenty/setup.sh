#!/usr/bin/env bash
# Creates .env with random secrets (only if it does not exist yet).
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then echo ".env already exists, leaving it alone."; exit 0; fi
umask 077
cat > .env <<ENVEOF
PG_PASSWORD=$(openssl rand -hex 16)
APP_SECRET=$(openssl rand -hex 32)
TWENTY_TAG=latest
ENVEOF
echo "Created .env"
