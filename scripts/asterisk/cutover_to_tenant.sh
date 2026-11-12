#!/usr/bin/env bash
# Re-point the single registered phone line (one Hero registration = one number = one business)
# at a different business, safely and reversibly.  Run ON the VPS as root.
#
#   bash cutover_to_tenant.sh <tenant-slug>            apply (refuses if preconditions fail)
#   bash cutover_to_tenant.sh --rollback <backup-dir>  undo using the directory the apply printed
#
# What it changes (nothing else):
#   1. tenants.phone_enabled for the new tenant, through the ADMIN API so the go-live gate runs
#   2. phone_numbers.tenant_id for the line (the number is a primary key: one tenant at a time)
#   3. /opt/trendi/shared/asterisk-routes.json and ASTERISK_ROUTES in /opt/trendi/shared/phone.env
#   4. generated/extensions.conf (pjsip.conf is NOT touched, so the registration is unaffected)
#   5. dialplan reload, then the BRIDGE container only (never the PBX)
#
# It deliberately does NOT write tenant_channel_authorizations. 'telephone' is the business
# owner's consent record (audited by a DB trigger); the script refuses to run until it exists.
set -euo pipefail

SHARED=/opt/trendi/shared
REL=/opt/trendi/releases/20261108-vps/product/scripts/asterisk
GEN=$REL/generated
PSQL='docker exec -i trendi-postgres-1 sh -c "psql -U \$POSTGRES_USER -d concierge -v ON_ERROR_STOP=1 -At"'
compose() { (cd "$REL" && docker compose -f compose.yml -f compose.public.yml --env-file "$SHARED/phone.env" "$@"); }
sql() { eval "$PSQL"; }                       # reads SQL on stdin
admin_patch() {                               # $1 slug  $2 json body  -> prints HTTP code
  local token; token=$(grep '^ADMIN_TOKEN=' "$SHARED/api.env" | cut -d= -f2-)
  curl -s -o /tmp/cutover-patch.json -w '%{http_code}' -X PATCH -H "X-Admin-Token: $token" \
       -H 'Content-Type: application/json' -d "$2" "http://127.0.0.1:8000/admin/tenants/$1"
}

swap_routes_tenant() {                        # $1 from-slug  $2 to-slug : edits routes json + phone.env
  python3 - "$1" "$2" <<'PY'
import json, re, sys
old, new = sys.argv[1], sys.argv[2]
path = '/opt/trendi/shared/asterisk-routes.json'
d = json.load(open(path))
changed = 0
for r in d['routes']:
    if r['tenant'] == old:
        r['tenant'] = new; changed += 1
assert changed == 1, f'expected exactly one route for {old}, found {changed}'
json.dump(d, open(path, 'w'))
routes = [{'tenant': r['tenant'], 'number': r['number'], 'port': r['port']} for r in d['routes']]
env = '/opt/trendi/shared/phone.env'
lines = open(env).read().splitlines()
out, seen = [], False
for line in lines:
    if line.startswith('ASTERISK_ROUTES='):
        out.append('ASTERISK_ROUTES=' + json.dumps(routes, separators=(',', ':'))); seen = True
    else:
        out.append(line)
assert seen, 'ASTERISK_ROUTES not found in phone.env'
open(env, 'w').write('\n'.join(out) + '\n')
print('routes now:', [(r['tenant'], r['port']) for r in routes])
PY
  chmod 600 "$SHARED/asterisk-routes.json" "$SHARED/phone.env"
}

render_extensions() {                         # renders into a temp dir and installs extensions.conf only
  local tmp; tmp=$(mktemp -d)
  (cd "$REL" && python3 render_routes.py "$SHARED/asterisk-routes.json" "$tmp" bridge 152.42.239.240)
  # Safety net: the registration file must be byte-identical or something is wrong.
  cmp -s "$tmp/pjsip.conf" "$GEN/pjsip.conf" || { echo "ABORT: rendered pjsip.conf differs from live"; rm -rf "$tmp"; return 1; }
  install -m 644 "$tmp/extensions.conf" "$GEN/extensions.conf"
  rm -rf "$tmp"
}

reload_and_restart_bridge() {
  docker exec asterisk-pbx-1 asterisk -rx 'dialplan reload' | tail -1
  compose up -d --force-recreate --no-deps bridge 2>&1 | tail -3
  for i in $(seq 1 20); do
    docker logs asterisk-bridge-1 --since 40s 2>&1 | grep -q 'private phone listener ready' && break; sleep 2
  done
}

verify() {                                    # $1 expected slug
  echo "== verify"
  docker logs asterisk-bridge-1 --since 90s 2>&1 | grep 'listener ready' | tail -2
  docker exec asterisk-pbx-1 asterisk -rx 'pjsip show registrations' | grep concierge-reg
  docker exec asterisk-pbx-1 asterisk -rx 'dialplan show concierge-ingress-1' | grep -m2 "business-$1" || { echo "!! dialplan does not point at $1"; return 1; }
  echo -n "PBX container uptime: "; docker inspect -f '{{.State.StartedAt}}' asterisk-pbx-1
  echo "OK: line now answers as $1"
}

# ---------------------------------------------------------------- rollback
if [ "${1:-}" = "--rollback" ]; then
  BK=${2:?give the backup dir printed by the apply}
  [ -f "$BK/state.env" ] || { echo "no state.env in $BK"; exit 1; }
  # shellcheck disable=SC1091
  . "$BK/state.env"                           # OLD_SLUG NEW_SLUG NUMBER
  echo "== rollback: $NEW_SLUG -> $OLD_SLUG using $BK"
  cp -a "$BK/asterisk-routes.json" "$SHARED/asterisk-routes.json"
  cp -a "$BK/phone.env" "$SHARED/phone.env"
  cp -a "$BK/extensions.conf" "$GEN/extensions.conf"
  sql <<SQL
UPDATE phone_numbers SET tenant_id=(SELECT id FROM tenants WHERE slug='$OLD_SLUG') WHERE e164='$NUMBER';
SQL
  admin_patch "$NEW_SLUG" '{"phone_enabled":false}' >/dev/null || true
  reload_and_restart_bridge
  verify "$OLD_SLUG"
  exit 0
fi

# ---------------------------------------------------------------- apply
NEW=${1:?usage: cutover_to_tenant.sh <tenant-slug> | --rollback <backup-dir>}
[[ "$NEW" =~ ^[a-z0-9][a-z0-9-]{0,79}$ ]] || { echo "bad slug"; exit 1; }

OLD=$(python3 -c "import json;r=json.load(open('$SHARED/asterisk-routes.json'))['routes'];assert len(r)==1;print(r[0]['tenant'])")
NUMBER=$(python3 -c "import json;print(json.load(open('$SHARED/asterisk-routes.json'))['routes'][0]['number'])")
[ "$OLD" != "$NEW" ] || { echo "line already answers as $NEW"; exit 0; }
echo "== cutting $NUMBER from $OLD to $NEW"

echo "== 1. preconditions"
AUTH=$(sql <<SQL
SELECT count(*) FROM tenant_channel_authorizations a JOIN tenants t ON t.id=a.tenant_id
WHERE t.slug='$NEW' AND a.channel='telephone' AND a.authorized;
SQL
)
if [ "$AUTH" != "1" ]; then
  echo "REFUSED: $NEW has not authorised telephone answering. The business owner must grant it in"
  echo "their owner portal (it is their consent record and is audited). Nothing was changed."
  exit 2
fi
echo "   telephone consent present"
docker exec asterisk-pbx-1 asterisk -rx 'pjsip show registrations' | grep -q Registered || { echo "REFUSED: Hero registration is not Registered"; exit 2; }
echo "   Hero registered"

echo "== 2. go-live gate (admin API, expects 200)"
CODE=$(admin_patch "$NEW" '{"phone_enabled":true}')
if [ "$CODE" != "200" ]; then echo "REFUSED: gate said HTTP $CODE"; cat /tmp/cutover-patch.json | head -c 600; echo; exit 2; fi
rm -f /tmp/cutover-patch.json

echo "== 3. backups"
BK=/opt/trendi/backups/phone-cutover-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BK" && chmod 700 "$BK"
cp -a "$SHARED/asterisk-routes.json" "$SHARED/phone.env" "$GEN/extensions.conf" "$GEN/pjsip.conf" "$BK/"
printf 'OLD_SLUG=%s\nNEW_SLUG=%s\nNUMBER=%s\n' "$OLD" "$NEW" "$NUMBER" > "$BK/state.env"
echo "   $BK"

echo "== 4. move the number, routes and dialplan"
sql <<SQL
UPDATE phone_numbers SET tenant_id=(SELECT id FROM tenants WHERE slug='$NEW'), enabled=true WHERE e164='$NUMBER';
SQL
swap_routes_tenant "$OLD" "$NEW"
render_extensions

echo "== 5. reload dialplan, recreate the bridge only"
reload_and_restart_bridge
verify "$NEW"
echo
echo "Applied. Undo with:  bash $0 --rollback $BK"
