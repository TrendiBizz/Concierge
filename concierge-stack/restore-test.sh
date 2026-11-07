#!/usr/bin/env bash
# Proves the backup can really be restored. Restores the newest snapshot into a throwaway folder,
# checks it, prints only counts (never names, numbers or message text), then deletes the folder.
#
#   ./concierge-stack/restore-test.sh
#
# A backup you have never restored is a hope, not a backup. Run this after the first backup and
# then every month.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${BACKUP_ENV:-$DIR/backup.env}"
if [[ ! -f "$ENV_FILE" ]]; then echo "Run ./concierge-stack/set-backup.sh first." >&2; exit 1; fi
if ! command -v restic >/dev/null 2>&1; then echo "restic is not installed. Run: brew install restic" >&2; exit 1; fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

TMP="$(mktemp -d)"
chmod 700 "$TMP"
TEMP_CONTAINER=""
cleanup() {
  if [[ -n "$TEMP_CONTAINER" ]]; then
    docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "Checking the repository is intact..."
restic check --quiet

echo "Restoring the newest snapshot to a temporary folder..."
restic restore latest --tag concierge --target "$TMP" --quiet

# The snapshot keeps the staging path that backup.sh used.
RESTORED="$TMP$DIR/.backup-stage/data"
if [[ ! -d "$RESTORED" ]]; then
  echo "FAILED: the restored snapshot has no data folder." >&2
  exit 1
fi

FAILED=0
if [[ -f "$RESTORED/concierge.db" ]]; then
  RESULT="$(sqlite3 "$RESTORED/concierge.db" 'PRAGMA integrity_check;')"
  if [[ "$RESULT" == "ok" ]]; then
    echo "bookings database: restored, integrity ok"
  else
    echo "bookings database: INTEGRITY CHECK FAILED" >&2
    FAILED=1
  fi
else
  echo "bookings database: none yet (no bookings have been made)"
fi
for f in messages.jsonl outbox.jsonl; do
  if [[ -f "$RESTORED/$f" ]]; then
    echo "$f: restored, $(wc -l < "$RESTORED/$f" | tr -d ' ') lines"
  else
    echo "$f: not present in this snapshot"
  fi
done
if [[ -d "$RESTORED/transcripts" ]]; then
  echo "transcripts: restored, $(find "$RESTORED/transcripts" -name '*.jsonl' | wc -l | tr -d ' ') files"
else
  echo "transcripts: none yet"
fi

# Verify Twenty's database can be restored into a fully disposable Postgres instance.
# Do not connect to the production network, ports, or Docker volumes.
TWENTY="$TMP$DIR/.backup-stage/twenty"
if [[ ! -s "$TWENTY/database.dump" || ! -d "$TWENTY/storage" ]]; then
  echo "Twenty CRM: database dump or storage missing from encrypted snapshot" >&2
  FAILED=1
elif ! command -v docker >/dev/null 2>&1; then
  echo "Twenty CRM: Docker unavailable for isolated restore test" >&2
  FAILED=1
else
  TEMP_CONTAINER="trendi-twenty-restore-$$"
  if docker run --rm -d --name "$TEMP_CONTAINER" --network none --memory 512m \
    -e POSTGRES_PASSWORD=temporary-restore-test-only \
    -e POSTGRES_DB=default \
    -v "$TWENTY:/restore:ro" postgres:16 >/dev/null; then
    READY=0
    for i in $(seq 1 45); do
      if docker exec "$TEMP_CONTAINER" pg_isready -U postgres -d default >/dev/null 2>&1; then
        READY=1
        break
      fi
      sleep 1
    done
    if [[ "$READY" -eq 1 ]] && docker exec "$TEMP_CONTAINER" \
      pg_restore -U postgres -d default --no-owner --no-acl --exit-on-error \
      /restore/database.dump >/dev/null 2>&1; then
      COUNT="$(docker exec "$TEMP_CONTAINER" psql -U postgres -d default -Atqc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema');")"
      if [[ "$COUNT" =~ ^[0-9]+$ ]] && (( COUNT > 0 )); then
        echo "Twenty CRM: isolated database restore passed ($COUNT tables); storage present"
      else
        echo "Twenty CRM: restored database has no application tables" >&2
        FAILED=1
      fi
    else
      echo "Twenty CRM: isolated PostgreSQL restore failed" >&2
      FAILED=1
    fi
  else
    echo "Twenty CRM: could not start isolated PostgreSQL" >&2
    FAILED=1
  fi
  docker rm -f "$TEMP_CONTAINER" >/dev/null 2>&1 || true
  TEMP_CONTAINER=""
fi

# When the private CRM ledger was active, require recovered receipt files.
# Never replay unfinished claims automatically: reconcile against Twenty first.
if [[ -f "$TWENTY/ledger.enabled" ]]; then
  if [[ ! -d "$TWENTY/ledger" ]]; then
    echo "CRM delivery ledger: missing from restored snapshot" >&2
    FAILED=1
  elif ! python3 - "$TWENTY/ledger" <<'PY'
import json, pathlib, re, sys
root=pathlib.Path(sys.argv[1])
valid=re.compile(r'^[a-f0-9]{64}$')
for file in root.iterdir():
    if not file.is_file():
        raise SystemExit(1)
    if file.suffix not in ('.claim','.done','.tmp'):
        raise SystemExit(1)
    key=file.name.split('.')[0]
    if not valid.fullmatch(key):
        raise SystemExit(1)
    if file.suffix in ('.claim','.done'):
        obj=json.loads(file.read_text())
        if file.suffix=='.claim' and obj.get('deliveryId')!=key:
            raise SystemExit(1)
        if file.suffix=='.done' and (obj.get('ok') is not True or
                obj.get('note') is not True or
                not valid.fullmatch(str(obj.get('fingerprint','')))):
            raise SystemExit(1)
print('CRM delivery ledger: encrypted restore files validated')
PY
  then
    echo "CRM delivery ledger: restored receipts invalid" >&2
    FAILED=1
  fi
fi

SOCIAL_DB="$TMP$DIR/.backup-stage/social/social.db"
if [[ -f "$SOCIAL_DB" ]]; then
  if [[ ! -s "$TMP$DIR/.backup-stage/social/social.env" ]]; then
    echo "social SQLite: vault-key configuration missing from backup" >&2
    FAILED=1
  fi
  if [[ "$(sqlite3 "$SOCIAL_DB" 'PRAGMA integrity_check;')" == "ok" ]]; then
    echo "social SQLite: restored, integrity ok"
  else
    echo "social SQLite: integrity check failed" >&2
    FAILED=1
  fi
else
  echo "social SQLite: not present (service not yet used)"
fi

if [[ "$FAILED" -eq 0 ]]; then
  echo "RESTORE TEST PASSED"
else
  echo "RESTORE TEST FAILED" >&2
  exit 1
fi
