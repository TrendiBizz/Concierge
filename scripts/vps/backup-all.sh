#!/usr/bin/env bash
# Full data backup of the Concierge VPS: both Postgres databases, Docker
# volumes, shared secrets/config, website and phone config. Keeps 14 daily
# archives under /opt/trendi/backups (root-only). Runs from cron daily.
set -euo pipefail
ROOT=/opt/trendi
BACKUPS="$ROOT/backups"
STAMP=$(date -u +%Y%m%d-%H%M%S)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$BACKUPS"
chmod 700 "$BACKUPS"
log() { echo "$(date -Is) $*"; }
log "backup start $STAMP"

docker exec trendi-postgres-1 pg_dump -U postgres -d concierge -Fc > "$WORK/concierge.dump"
docker exec trendi-crm-db-1 sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$WORK/crm.dump"

for spec in "trendi_social:social" "trendi_crm-storage:crm-storage"; do
  volume="${spec%%:*}"
  name="${spec##*:}"
  docker run --rm -v "$volume":/data:ro -v "$WORK":/backup alpine:3.20 \
    tar czf "/backup/$name.tgz" -C /data .
done

tar czf "$WORK/shared.tgz" -C "$ROOT" shared
tar czf "$WORK/website.tgz" -C "$ROOT/releases/20261108-vps" website/site
tar czf "$WORK/asterisk.tgz" -C "$ROOT/releases/20261108-vps/product/scripts" asterisk/generated

(cd "$WORK" && sha256sum * > SHA256SUMS)
ARCHIVE="$BACKUPS/trendi-backup-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$WORK" .
chmod 600 "$ARCHIVE"

# Keep the newest 14 daily archives.
ls -t "$BACKUPS"/trendi-backup-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
log "backup done $(du -h "$ARCHIVE" | cut -f1) $ARCHIVE"
