#!/usr/bin/env bash
set -euo pipefail
umask 077
set -a
source /opt/trendi/shared/backup.env
set +a
export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/opt/trendi/backups/restic-cache}"
mkdir -p "$RESTIC_CACHE_DIR"
exec python3 /opt/trendi/releases/20261108-vps/product/scripts/vps/restore-test.py
