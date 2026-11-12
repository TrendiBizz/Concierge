#!/usr/bin/env bash
# Dump every database to ./backups/<timestamp>/*.sql.gz and keep the last 14 days.
# Run from cron, e.g.:  15 3 * * *  /path/to/concierge/scripts/backup.sh
# Then copy ./backups off the server (rclone to Backblaze B2 / S3 / Google Drive).
set -euo pipefail

cd "$(dirname "$0")/.."

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="backups/${STAMP}"
mkdir -p "${OUT}"

for db in concierge chatwoot twenty; do
  echo "Dumping ${db}..."
  docker compose exec -T postgres pg_dump -U postgres --no-owner "${db}" | gzip > "${OUT}/${db}.sql.gz"
done

# Remove backup folders older than 14 days.
find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +

echo "Backup written to ${OUT}"
