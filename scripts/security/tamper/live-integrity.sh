#!/usr/bin/env bash
# Daily tamper check for https://trendibizz.com against the repo's website/ tree.
#   bash scripts/security/tamper/live-integrity.sh [--site DIR | --known-good DIR]
# Exit 0 PASS · 1 mismatch/tamper (report in reports/) · 2 network error
# A FAIL < 30 min after a deploy is re-checked once after 6 min (edge caches such
# as max-age=300 on JS/CSS need time to turn over).
# Set LIVE_INTEGRITY_NO_RETRY=1 to skip the wait.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${TRENDI_SITE_ROOT:-$(cd "$HERE/../../.." && pwd)}"
SITE="$ROOT/website"
python3 "$HERE/live_integrity.py" "$@"; rc=$?
if [[ $rc -eq 1 && -z "${LIVE_INTEGRITY_NO_RETRY:-}" && -f "$SITE/index.html" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$SITE/index.html" 2>/dev/null || stat -c %Y "$SITE/index.html") ))
  if (( age < 1800 )); then
    echo "[live-integrity] website/ changed ${age}s ago — re-checking once in 6 min (cache propagation)…"
    sleep 360
    python3 "$HERE/live_integrity.py" "$@"; rc=$?
  fi
fi
exit $rc
