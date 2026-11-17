#!/usr/bin/env bash
# Daily tamper + unexpected-change watch for trendibizz.com. READ-ONLY.
#   bash scripts/security/daily-watch.sh --cf-snapshot <file>      run (file from cf-snapshot.js via Cloudflare MCP)
#   bash scripts/security/daily-watch.sh accept --reason 'Omega Boss: DNSSEC on' dns dnssec public_dns
#   bash scripts/security/daily-watch.sh accept --reason '...'      (no sections = all)
# Exit 0 all clear · 1 change/problem · 2 could not check (nothing changed)
# Report: scripts/security/reports/daily-watch-latest.txt   Baselines: scripts/security/baselines/
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# Portable lock (macOS has no flock): mkdir is atomic; stale locks older than 30 min are cleared.
LOCK="/tmp/trendi-daily-watch.lock.d"
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; fi
if ! mkdir "$LOCK" 2>/dev/null; then echo "daily-watch: another run is in progress" >&2; exit 2; fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
python3 "$HERE/daily_watch.py" "$@"
