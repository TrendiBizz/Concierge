#!/usr/bin/env bash
# Full data backup of the Concierge VPS: both Postgres databases, Podman
# volumes, shared secrets/config, website and phone config. Keeps 14 daily
# archives under /opt/trendi/backups (root-only). Runs from cron daily.
set -euo pipefail
ROOT=/opt/trendi
BACKUPS="$ROOT/backups"
STAMP=$(date -u +%Y%m%d-%H%M%S)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$BACKUPS"
chown root:999 "$BACKUPS"
chmod 750 "$BACKUPS"
log() { echo "$(date -Is) $*"; }
log "backup start $STAMP"

podman exec trendi-postgres-1 pg_dump -U postgres -d concierge -Fc > "$WORK/concierge.dump"

SKIPPED=()
volumes=("trendi_social:social")

for spec in "${volumes[@]}"; do
  volume="${spec%%:*}"
  name="${spec##*:}"
  podman run --rm -v "$volume":/data:ro -v "$WORK":/backup alpine:3.20 \
    tar czf "/backup/$name.tgz" -C /data .
done
printf '%s\n' "${SKIPPED[@]:-}" > "$WORK/SKIPPED.txt"

tar czf "$WORK/shared.tgz" --exclude="shared/media" -C "$ROOT" shared
tar czf "$WORK/website.tgz" -C "$ROOT/releases/20261108-vps" website/site
tar czf "$WORK/asterisk.tgz" -C "$ROOT/releases/20261108-vps/product/scripts" asterisk/generated

(cd "$WORK" && sha256sum * > SHA256SUMS)
ARCHIVE="$BACKUPS/trendi-backup-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$WORK" .
chown root:999 "$ARCHIVE"
chmod 640 "$ARCHIVE"

# Keep the newest 14 daily archives.
ls -t "$BACKUPS"/trendi-backup-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
log "backup done $(du -h "$ARCHIVE" | cut -f1) $ARCHIVE"
