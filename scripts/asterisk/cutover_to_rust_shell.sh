#!/usr/bin/env bash
# Point the phone line's dialplan at the Rust telephone shell instead of the Python bridge, safely and reversibly.
# Run ON the VPS as root.
#
#   bash cutover_to_rust_shell.sh                    apply (refuses if a precondition fails)
#   bash cutover_to_rust_shell.sh --rollback <dir>   undo using the directory the apply printed
#
# What it changes (nothing else):
#   1. generated/extensions.conf: the host in each AudioSocket(...) line becomes the shell (172.30.91.3)
#   2. a dialplan reload
# It does NOT touch pjsip.conf (so the carrier registration is unaffected), the database, the routes, the PBX
# container, the Python bridge or the shell container. The Python bridge keeps running at 172.30.91.4 as the fallback.
set -euo pipefail

SHARED=${SHARED:-/opt/trendi/shared}
REL=${REL:-/opt/trendi/releases/20261108-vps/product/scripts/asterisk}
GEN=$REL/generated
SHELL_HOST=${SHELL_HOST:-172.30.91.3}        # fixed address of the shell on the phone network (scripts/vps/compose.yml)
PUBLIC_IP=${PUBLIC_IP:-152.42.239.240}       # same value cutover_to_tenant.sh passes to render_routes.py
PBX=${PBX:-asterisk-pbx-1}
SHELL_CT=${SHELL_CT:-trendi-shell-1}

render_with_host() {                          # $1 host -> installs extensions.conf only
  local host="$1" tmp
  tmp=$(mktemp -d)
  (cd "$REL" && python3 render_routes.py "$SHARED/asterisk-routes.json" "$tmp" "$host" "$PUBLIC_IP")
  # Safety net: the registration file must be byte-identical or something is wrong.
  cmp -s "$tmp/pjsip.conf" "$GEN/pjsip.conf" || { echo "ABORT: rendered pjsip.conf differs from live"; rm -rf "$tmp"; return 1; }
  # The PBX bind-mounts this file by inode: write through the existing inode (cat >), never mv/cp/install,
  # or the container keeps the old file and `dialplan reload` is a no-op.
  cat "$tmp/extensions.conf" > "$GEN/extensions.conf"
  chmod 644 "$GEN/extensions.conf"
  rm -rf "$tmp"
}

reload_dialplan() { docker exec "$PBX" asterisk -rx 'dialplan reload' | tail -1; }

audiosocket_targets() {
  docker exec "$PBX" asterisk -rx 'dialplan show concierge-ingress-1' | grep -o 'AudioSocket([^)]*)' | sort -u
}

# ---------------------------------------------------------------- rollback
if [ "${1:-}" = "--rollback" ]; then
  BK=${2:?give the backup dir printed by the apply}
  [ -f "$BK/extensions.conf" ] || { echo "no extensions.conf in $BK"; exit 1; }
  echo "== rollback using $BK"
  cat "$BK/extensions.conf" > "$GEN/extensions.conf"
  chmod 644 "$GEN/extensions.conf"
  reload_dialplan
  echo "== dialplan now sends calls to:"
  audiosocket_targets
  echo "Rolled back: the Python bridge answers again."
  exit 0
fi

# ---------------------------------------------------------------- apply
echo "== 1. preconditions"
[ "$(docker inspect -f '{{.State.Status}}' "$SHELL_CT" 2>/dev/null)" = running ] \
  || { echo "REFUSED: $SHELL_CT is not running"; exit 2; }
echo "   shell container running"

PORTS=$(python3 -c "import json;print(' '.join(str(r['port']) for r in json.load(open('$SHARED/asterisk-routes.json'))['routes']))")
[ -n "$PORTS" ] || { echo "REFUSED: no routes in $SHARED/asterisk-routes.json"; exit 2; }
for port in $PORTS; do
  # A socket in LISTEN state (0A) on this port, read from inside the shell container. No log scraping: old log
  # lines from an earlier start must not be able to satisfy this.
  HEX=$(printf '%04X' "$port")
  docker exec "$SHELL_CT" sh -c "grep -qE ':$HEX [0-9A-F:]+ 0A ' /proc/net/tcp /proc/net/tcp6" \
    || { echo "REFUSED: the shell is not listening on route port $port (check ASTERISK_ROUTES in compose.env)"; exit 2; }
done
echo "   shell listening on route ports: $PORTS"

# The shell talks to the API over /internal/voice/*. A wrong token must give 401; 503 means INTERNAL_TOKEN is unset.
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H 'x-concierge-internal: wrong' \
       -d '{"tenant_id":"x","record_session_id":"x"}' http://127.0.0.1:8000/internal/voice/monitor)
[ "$CODE" = 401 ] || { echo "REFUSED: internal voice API answered HTTP $CODE (expected 401). 503 = INTERNAL_TOKEN unset in api.env."; exit 2; }
echo "   internal voice API enabled and rejecting a bad token"

docker exec "$PBX" asterisk -rx 'pjsip show registrations' | grep -q Registered \
  || { echo "REFUSED: the carrier registration is not Registered"; exit 2; }
echo "   carrier registered"

ACTIVE=$(docker exec "$PBX" asterisk -rx 'core show channels count' | grep -o '^[0-9]* active call' | grep -o '^[0-9]*' || echo 0)
[ "${ACTIVE:-0}" = 0 ] || { echo "REFUSED: $ACTIVE call(s) in progress; try again when the line is quiet"; exit 2; }
echo "   no calls in progress"

echo "== 2. backup"
BK=${BACKUPS:-/opt/trendi/backups}/rust-shell-cutover-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BK" && chmod 700 "$BK"
cp -a "$GEN/extensions.conf" "$GEN/pjsip.conf" "$BK/"
echo "   $BK"

echo "== 3. point the dialplan at the Rust shell ($SHELL_HOST) and reload"
render_with_host "$SHELL_HOST"
reload_dialplan
TARGETS=$(audiosocket_targets)
echo "$TARGETS"
echo "$TARGETS" | grep -q "$SHELL_HOST" || { echo "!! dialplan does not point at the shell; rolling back"; bash "$0" --rollback "$BK"; exit 1; }
if echo "$TARGETS" | grep -qv "$SHELL_HOST"; then echo "!! some AudioSocket lines still point elsewhere; rolling back"; bash "$0" --rollback "$BK"; exit 1; fi

echo
echo "Applied: the Rust shell now answers. Place one test call now (greeting, audio both ways, transcript in the CRM)."
echo "Undo at any time with:  bash $0 --rollback $BK"
