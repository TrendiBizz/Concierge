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
# Caddyfile intentionally sets 'admin off' (no localhost:2019 admin socket),
# so reload via container restart after config validation.
podman restart trendi-gateway-1 >/dev/null
for i in 1 2 3 4 5 6 7 8 9 10; do
    state=\$(podman inspect -f '{{.State.Running}}' trendi-gateway-1 2>/dev/null || true)
    [ \"\$state\" = 'true' ] && break
    sleep 1
done
[ \"\$(podman inspect -f '{{.State.Running}}' trendi-gateway-1)\" = 'true' ]
echo 'gateway reloaded'
"
