#!/usr/bin/env bash
# Move the uploads folder of the removed 3D/Designs feature aside on the box. Nothing is deleted:
# /opt/trendi/shared/designs is MOVED to /opt/trendi/shared/removed/designs-<date>/ so it can be put back.
# Prints the file list first. Safe to re-run (no-op once the folder is gone).
#
# Usage:  KEY=./Concierge ./scripts/vps/archive-designs.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" 'set -e
  src=/opt/trendi/shared/designs; dest=/opt/trendi/shared/removed/designs-$(date +%Y%m%d)
  [ -d "$src" ] || { echo "nothing to archive ($src absent)"; exit 0; }
  find "$src" -type f -exec ls -la {} \;
  mkdir -p /opt/trendi/shared/removed; mv "$src" "$dest"; echo "moved $src -> $dest"'
