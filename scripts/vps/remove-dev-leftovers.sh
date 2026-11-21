#!/usr/bin/env bash
# List and safely remove leftover dev-* containers, their unused images, volumes and networks
# on the VPS, backing up any volume with data first and removing containerd only if Podman does
# not depend on it (Jo, 2026-11-21).
#
# Usage:
#   KEY=<deploy key> ./scripts/vps/remove-dev-leftovers.sh --dry-run
#   KEY=<deploy key> ./scripts/vps/remove-dev-leftovers.sh --apply
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
SCRIPT="$REPO_ROOT/scripts/vps/remove_dev_leftovers.py"

MODE="--dry-run"
if [ "${1:-}" = "--apply" ] || [ "${1:-}" = "--dry-run" ]; then
  MODE="$1"
  shift
elif [ "$#" -gt 0 ]; then
  echo "Usage: $0 [--dry-run|--apply]" >&2
  exit 2
fi

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "REL='$RELEASE' python3 - '$MODE' --release '$RELEASE'" < "$SCRIPT"
