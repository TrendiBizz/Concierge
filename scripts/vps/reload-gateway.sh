#!/usr/bin/env bash
# Validate the published Caddyfile, then load it into the running gateway WITHOUT restarting the container.
#
# Why: sync-tooling.sh copies the Caddyfile to the box, but Caddy only reads it at start. A new route (for example
# /api/robots, 2026-11-24) stayed dead until someone restarted the gateway by hand, and no script did that.
# sync-tooling.sh now calls this after every sync, so a Caddyfile change always goes live.
#
# What it does, on the box:
#   1. copies the published Caddyfile into the gateway container (a bind-mounted single file can lag behind an
#      rsync, which replaces the file) and runs `caddy validate` on that copy. INVALID => abort; the running
#      config is never touched.
#   2. `caddy reload` (graceful: in-flight requests finish, nothing restarts, no dropped connections).
#   3. Only if the running config has no admin API (the one-time case: it was started with `admin off`, before
#      the Caddyfile enabled `admin localhost:2019`), it falls back to ONE `podman restart` of the gateway and
#      says so. That is the only case in which this script restarts anything.
#
# Usage:  KEY=./Concierge ./scripts/vps/reload-gateway.sh
#         GATEWAY_CADDYFILE_LOCAL=/path/to/Caddyfile  validate (and load) that file instead of the published one
#         GATEWAY_VALIDATE_ONLY=1                    validate and stop (changes nothing)
# Exit:   0 only when the gateway is running the validated Caddyfile.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
GATEWAY="${GATEWAY_CONTAINER:-trendi-gateway-1}"
PUBLISHED="$RELEASE/product/scripts/vps/Caddyfile"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")

SOURCE="$PUBLISHED"
if [ -n "${GATEWAY_CADDYFILE_LOCAL:-}" ]; then
  [ -f "$GATEWAY_CADDYFILE_LOCAL" ] || { echo "no such file: $GATEWAY_CADDYFILE_LOCAL" >&2; exit 1; }
  SOURCE="/tmp/Caddyfile.candidate.$$"
  scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$GATEWAY_CADDYFILE_LOCAL" "$HOST:$SOURCE"
fi

"${SSH[@]}" "$HOST" "set -e
SOURCE='$SOURCE'; GATEWAY='$GATEWAY'; VALIDATE_ONLY='${GATEWAY_VALIDATE_ONLY:-0}'
cleanup() { podman exec \"\$GATEWAY\" rm -f /tmp/Caddyfile.new >/dev/null 2>&1 || true; case \"\$SOURCE\" in /tmp/Caddyfile.candidate.*) rm -f \"\$SOURCE\";; esac; }
trap cleanup EXIT
podman cp \"\$SOURCE\" \"\$GATEWAY:/tmp/Caddyfile.new\"
if ! podman exec \"\$GATEWAY\" caddy validate --config /tmp/Caddyfile.new --adapter caddyfile 2>&1; then
  echo 'ABORT: the Caddyfile is invalid; the running gateway was not touched.' >&2
  exit 1
fi
echo 'Caddyfile is valid'
[ \"\$VALIDATE_ONLY\" = 1 ] && exit 0
if podman exec \"\$GATEWAY\" wget -q -O /dev/null --timeout=3 http://localhost:2019/config/ 2>/dev/null; then
  podman exec \"\$GATEWAY\" caddy reload --config /tmp/Caddyfile.new --adapter caddyfile
  echo 'gateway reloaded gracefully (no restart)'
else
  echo 'running config has no admin API (one-time bootstrap): restarting the gateway once to adopt the Caddyfile'
  podman restart \"\$GATEWAY\" >/dev/null
  for i in 1 2 3 4 5 6 7 8 9 10; do
    [ \"\$(podman inspect -f '{{.State.Running}}' \"\$GATEWAY\" 2>/dev/null || true)\" = true ] && break
    sleep 1
  done
  [ \"\$(podman inspect -f '{{.State.Running}}' \"\$GATEWAY\")\" = true ]
  echo 'gateway restarted with the new Caddyfile'
fi
"
