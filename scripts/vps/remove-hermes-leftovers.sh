#!/usr/bin/env bash
# Remove Hermes leftovers from the box (Jo, 2026-11-21). Nothing is deleted outright except unused images,
# the idle buildx container and the Docker engine package; files are moved aside or backed up first.
#
#   1. /opt/trendi/shared/hermes/ -> $RELEASE/removed/20261121/shared/hermes/
#   2. HERMES_* lines in api.env removed (backup api.env.bak-<date>-hermes first; values never printed)
#   3. images trendi-hermes-gateway and nousresearch/hermes-agent removed (podman refuses if in use)
#   4. buildx_buildkit_default container removed (and its moby/buildkit image if unused)
#   5. docker.io (Docker engine) removed ONLY if the daemon is inactive, then the compose provider and
#      the docker.sock -> podman link are re-checked. Data in /var/lib/docker is left in place.
# The api must be restarted afterwards for the api.env change (deploy-api.sh does that).
#
# Usage:  KEY=<deploy key> ./scripts/vps/remove-hermes-leftovers.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "REL='$RELEASE' bash -s" <<'REMOTE'
set -euo pipefail
D=20261121
DEST="$REL/removed/$D/shared"
if [ -d /opt/trendi/shared/hermes ]; then
  mkdir -p "$DEST"; mv /opt/trendi/shared/hermes "$DEST/hermes"; echo "moved shared/hermes -> $DEST/hermes"
else echo "shared/hermes: already gone"; fi

ENVF=/opt/trendi/shared/api.env
if grep -q '^HERMES_' "$ENVF"; then
  cp -p "$ENVF" "$ENVF.bak-$D-hermes"
  n=$(grep -c '^HERMES_' "$ENVF")
  grep -v '^HERMES_' "$ENVF" > "$ENVF.new"; chmod 600 "$ENVF.new"; mv "$ENVF.new" "$ENVF"
  echo "api.env: removed $n HERMES_* line(s); backup api.env.bak-$D-hermes"
else echo "api.env: no HERMES_* keys"; fi

for img in $(podman images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | awk '$1 ~ /trendi-hermes-gateway|nousresearch\/hermes-agent/ {print $2}' | sort -u); do
  if podman rmi "$img" >/dev/null 2>&1; then echo "image $img removed"; else echo "image $img NOT removed (in use?)"; fi
done

if podman container exists buildx_buildkit_default; then
  podman rm -f buildx_buildkit_default >/dev/null && echo "container buildx_buildkit_default removed"
  podman rmi docker.io/moby/buildkit:buildx-stable-1 >/dev/null 2>&1 && echo "image moby/buildkit removed" || true
fi

if dpkg -s docker.io >/dev/null 2>&1; then
  if [ "$(systemctl is-active docker 2>/dev/null || true)" = "active" ]; then
    echo "docker daemon is ACTIVE: leaving docker.io installed"
  else
    systemctl disable docker docker.socket >/dev/null 2>&1 || true
    apt-get remove -y docker.io >/dev/null 2>&1 && echo "docker.io removed (/var/lib/docker kept)"
  fi
else echo "docker.io: not installed"; fi

# compose must still work through podman, and docker.sock must still point at podman
[ "$(readlink /var/run/docker.sock)" = "/run/podman/podman.sock" ] || { echo "docker.sock link broken" >&2; exit 1; }
podman compose -f "$REL/product/scripts/vps/compose.yml" --env-file /opt/trendi/shared/compose.env --profile public config -q >/dev/null 2>&1 \
  && echo "podman compose config: ok" || { echo "podman compose config FAILED" >&2; exit 1; }
REMOTE
