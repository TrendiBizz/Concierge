#!/usr/bin/env bash
# Tag the images that are live right now so a bad deploy can be rolled back by retagging.
#
# Usage:  KEY=./Concierge ./scripts/vps/tag-rollback.sh rollback-pre-hermes-docker-20261121
# Tags trendi-concierge-api:vps and trendi-concierge-social:vps as :<tag>. Read-only for the
# running containers; refuses to overwrite an existing tag.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
TAG="${1:?usage: tag-rollback.sh <tag>}"
case "$TAG" in *[!A-Za-z0-9._-]*|"") echo "bad tag" >&2; exit 2 ;; esac

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "set -e
for img in trendi-concierge-api trendi-concierge-social; do
  if podman image exists \$img:$TAG; then echo \"REFUSING: \$img:$TAG already exists\" >&2; exit 1; fi
  podman tag \$img:vps \$img:$TAG
  echo \"tagged \$img:vps -> \$img:$TAG (\$(podman image inspect \$img:$TAG --format '{{.Id}}' | cut -c1-12))\"
done"
