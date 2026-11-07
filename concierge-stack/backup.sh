#!/usr/bin/env bash
# Encrypted backup of concierge-stack/data (bookings, messages, outbox, transcripts) with restic.
#
#   ./concierge-stack/backup.sh
#
# Settings come from concierge-stack/backup.env (create it with set-backup.sh). To test without a
# cloud account, point BACKUP_ENV at a file whose RESTIC_REPOSITORY is a local folder.
#
# What it does: makes a consistent copy of the SQLite database, adds the other data files, encrypts
# and uploads them, then deletes snapshots older than BACKUP_KEEP_DAYS. It prints no file contents
# and no secrets. Audio is not part of this: no audio is recorded yet.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${BACKUP_ENV:-$DIR/backup.env}"
if [[ ! -f "$ENV_FILE" ]]; then echo "Run ./concierge-stack/set-backup.sh first." >&2; exit 1; fi
if ! command -v restic >/dev/null 2>&1; then echo "restic is not installed. Run: brew install restic" >&2; exit 1; fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DATA="${DATA_DIR:-$DIR/data}"
if [[ ! -d "$DATA" ]]; then echo "No data folder at $DATA. Nothing to back up." >&2; exit 1; fi

# A fixed staging path keeps restic's change detection working between runs.
STAGE="$DIR/.backup-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/data"
chmod 700 "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

# SQLite must be copied with its own backup command: copying a live database file can capture it
# half-written.
if [[ -f "$DATA/concierge.db" ]]; then
  sqlite3 "$DATA/concierge.db" ".backup '$STAGE/data/concierge.db'"
fi
rsync -a --exclude 'concierge.db' --exclude 'concierge.db-*' "$DATA/" "$STAGE/data/"

# Twenty CRM is the system of record for leads. Capture a consistent PostgreSQL dump
# and the Twenty local-upload volume into the same encrypted restic snapshot.
# Fail closed: an unavailable database must not produce a "successful" backup.
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to back up Twenty CRM." >&2
  exit 1
fi
mkdir -p "$STAGE/twenty"
docker exec concierge-twenty-db-1 pg_dump -U postgres -d default --format=custom --no-owner --no-acl > "$STAGE/twenty/database.dump"
if [[ ! -s "$STAGE/twenty/database.dump" ]]; then
  echo "Twenty database dump is empty." >&2
  exit 1
fi
# Social-service drafts, account ciphertext and audit records share one SQLite DB.
# Use SQLite's online backup operation to capture a coherent snapshot.
SOCIAL_DB="$DIR/social-service/data/social.db"
mkdir -p "$STAGE/social"
if [[ -f "$SOCIAL_DB" ]]; then
  sqlite3 "$SOCIAL_DB" ".backup '$STAGE/social/social.db'"
fi
# Without the key, the restored encrypted social account tokens cannot be opened.
# restic encrypts this entire stage before remote storage.
SOCIAL_ENV="$DIR/social-service/data/social.env"
if [[ -f "$SOCIAL_DB" && ! -s "$SOCIAL_ENV" ]]; then
  echo "Social database exists but its vault-key configuration is missing." >&2
  exit 1
fi
if [[ -f "$SOCIAL_ENV" ]]; then
  install -m 600 "$SOCIAL_ENV" "$STAGE/social/social.env"
fi

mkdir -p "$STAGE/twenty/storage"
docker cp "concierge-twenty-server-1:/app/packages/twenty-server/.local-storage/." "$STAGE/twenty/storage/"

# Optional private CRM receipt ledger. When its Docker volume exists, the
# encrypted snapshot MUST include it or operator recovery could resend notes.
LEDGER_VOLUME="concierge_twenty-bridge-ledger"
if docker volume inspect "$LEDGER_VOLUME" >/dev/null 2>&1; then
  mkdir -p "$STAGE/twenty/ledger"
  chmod 700 "$STAGE/twenty/ledger"
  docker run --rm --network none --read-only --memory 128m \
    -v "$LEDGER_VOLUME:/ledger:ro" \
    -v "$STAGE/twenty/ledger:/backup" \
    postgres:16 sh -c 'cp -a /ledger/. /backup/'
  touch "$STAGE/twenty/ledger.enabled"
fi

# First run: create the encrypted repository.
if ! restic cat config >/dev/null 2>&1; then
  echo "Creating the encrypted backup repository (first run)."
  restic init >/dev/null
fi

restic backup "$STAGE/data" "$STAGE/twenty" "$STAGE/social" --tag concierge --host trendi-concierge --quiet
echo "Backup uploaded."

DAYS="${BACKUP_KEEP_DAYS:-30}"
restic forget --tag concierge --keep-within "${DAYS}d" --keep-last 3 --prune --quiet
echo "Snapshots older than ${DAYS} days removed (the newest 3 are always kept)."
restic snapshots --tag concierge --latest 3 --compact
