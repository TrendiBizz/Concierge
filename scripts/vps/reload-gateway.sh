#!/usr/bin/env bash
# Validate and reload the Caddy gateway container after Caddyfile changes.
#
# Usage:  KEY=./Concierge ./scripts/vps/reload-gateway.sh
# Run `sync-tooling.sh` first so the updated Caddyfile is on the box.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "set -e
podman exec trendi-gateway-1 caddy validate --config /etc/caddy/Caddyfile
podman exec trendi-gateway-1 caddy reload --config /etc/caddy/Caddyfile --force
echo 'gateway reloaded'
"
