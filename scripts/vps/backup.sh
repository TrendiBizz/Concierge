#!/usr/bin/env bash
# Existing encrypted R2 repository; credentials are root-only and never logged.
set -euo pipefail
umask 077
set -a
source /opt/trendi/shared/backup.env
set +a
export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/opt/trendi/backups/restic-cache}"
mkdir -p "$RESTIC_CACHE_DIR"
exec python3 /opt/trendi/releases/20261108-vps/product/scripts/vps/backup.py
