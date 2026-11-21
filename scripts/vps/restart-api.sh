#!/usr/bin/env bash
# Restart/recreate the API and reattach the social container without rebuilding the image.
#
# social uses `network_mode: service:api`, so restarting api on its own under Podman either fails
# or leaves social attached to a dead network namespace. Always delegate to redeploy-api.sh --no-build.
#
# Usage (on the VPS):  bash /opt/trendi/releases/20261108-vps/product/scripts/vps/restart-api.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/redeploy-api.sh" --no-build "$@"
