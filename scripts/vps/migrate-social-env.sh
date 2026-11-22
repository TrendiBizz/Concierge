#!/usr/bin/env bash
# Safely back up and migrate legacy social.env + social.db + social media into Concierge API/Postgres.
#
# - Creates timestamped backups of api.env, social.env, and social.db under /opt/trendi/backups/
# - Never deletes legacy social.env, social.db, or trendi_social volume
# - Never prints secret values
# - Idempotent: safe to re-run
set -euo pipefail

SHARED="/opt/trendi/shared"
BACKUPS="/opt/trendi/backups"
TS="$(date -u +%Y%m%d-%H%M%S)"
API_ENV="$SHARED/api.env"
SOCIAL_ENV="$SHARED/social.env"

mkdir -p "$BACKUPS" "$SHARED/media/social"
chmod 700 "$BACKUPS"

echo "==> backing up api.env and social.env ($TS)"
cp -p "$API_ENV" "$BACKUPS/api.env.$TS.bak"
chmod 600 "$BACKUPS/api.env.$TS.bak"
if [ -f "$SOCIAL_ENV" ]; then
  cp -p "$SOCIAL_ENV" "$BACKUPS/social.env.$TS.bak"
  chmod 600 "$BACKUPS/social.env.$TS.bak"
fi

echo "==> merging SOCIAL_* and META_* keys into api.env (values hidden)"
python3 - "$API_ENV" "$SOCIAL_ENV" <<'PY'
import sys
from pathlib import Path

api_path = Path(sys.argv[1])
soc_path = Path(sys.argv[2])

def parse_env(path: Path) -> dict[str, str]:
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out

api_map = parse_env(api_path)
soc_map = parse_env(soc_path)

skip_keys = {
    "SOCIAL_BIND",
    "SOCIAL_DB",
    "SOCIAL_AGENT_KEY",
    "SOCIAL_CONCIERGE_KEY",
    "SOCIAL_VAULT_KEY",
}

added = []
lines = []
for k, v in sorted(soc_map.items()):
    if not k.startswith("SOCIAL_") or k in skip_keys or not v:
        continue
    if k not in api_map:
        lines.append(f"{k}={v}")
        added.append(k)

# Ensure META_APP_ID is populated from SOCIAL_FACEBOOK_CLIENT_ID if unset
if "META_APP_ID" not in api_map and soc_map.get("SOCIAL_FACEBOOK_CLIENT_ID"):
    lines.append(f"META_APP_ID={soc_map['SOCIAL_FACEBOOK_CLIENT_ID']}")
    added.append("META_APP_ID")

# Record the dedicated WhatsApp Meta app ("Trendi Messaging") ID if unset
# (Embedded Signup remains OFF until META_WA_APP_SECRET and META_WA_EMBEDDED_SIGNUP_CONFIG_ID are set)
if "META_WA_APP_ID" not in api_map:
    lines.append("META_WA_APP_ID=29227891546892110")
    added.append("META_WA_APP_ID")

# Normalize Meta Graph version to v22.0 if unset
if "META_GRAPH_VERSION" not in api_map:
    lines.append("META_GRAPH_VERSION=v22.0")
    added.append("META_GRAPH_VERSION")

if lines:
    with api_path.open("a", encoding="utf-8") as fh:
        fh.write("\n# Merged from legacy social.env on unified social module migration\n")
        for ln in lines:
            fh.write(ln + "\n")

print("added_keys:", ",".join(added) if added else "(none - already present)")
PY

VOL_DIR="$(podman volume inspect trendi_social --format '{{.Mountpoint}}' 2>/dev/null || true)"
if [ -n "$VOL_DIR" ] && [ -f "$VOL_DIR/social.db" ]; then
  BACKUP_DB="$BACKUPS/social-legacy-$TS.db"
  install -m 600 -o 10001 -g 10001 "$VOL_DIR/social.db" "$BACKUP_DB"
  echo "==> backed up legacy social.db to $BACKUP_DB"

  if [ -d "$VOL_DIR/media" ]; then
    echo "==> copying legacy social media into $SHARED/media/social/"
    cp -an "$VOL_DIR/media/." "$SHARED/media/social/" 2>/dev/null || true
    chown -R 10001:10001 "$SHARED/media/social" 2>/dev/null || true
  fi

  # Extract SOCIAL_VAULT_KEY without printing it and pass via env into the api container
  VAULT_KEY="$(python3 -c '
from pathlib import Path
for ln in Path("/opt/trendi/shared/social.env").read_text().splitlines():
    if ln.startswith("SOCIAL_VAULT_KEY="):
        print(ln.split("=", 1)[1].strip(), end="")
        break
')"
  if [ -n "$VAULT_KEY" ]; then
    REL="${REL:-/opt/trendi/releases/20261108-vps/product}"
    echo "==> migrating legacy social.db rows into Concierge Postgres (re-encrypting with N9 vault)"
    podman exec -i \
      -e "SOCIAL_VAULT_KEY=$VAULT_KEY" \
      -e "LEGACY_SOCIAL_DB=/backups/social-legacy-$TS.db" \
      trendi-api-1 python3 - < "$REL/scripts/vps/migrate-social-db.py"
  else
    echo "WARNING: SOCIAL_VAULT_KEY not found in social.env; skipped token migration" >&2
  fi
else
  echo "==> no legacy social.db found; skipping SQLite migration"
fi
echo "==> migration script complete"
