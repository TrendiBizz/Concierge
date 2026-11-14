#!/usr/bin/env bash
# Wrapper for healthcheck.py: run it from cron every five minutes.
#
#   */5 * * * * /opt/trendi/releases/20261108-vps/product/scripts/vps/healthcheck.sh
#
# Exit 0 = healthy. Exit 1 = at least one failing check (so cron also mails root).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /opt/trendi/monitoring

LOG=/opt/trendi/monitoring/health.log

# Keep stdout pure JSON. This used to be `2>&1 | tee -a "$LOG"`, which merged the check's notes
# ("deploy grace: ...") and any traceback into the report: alert.sh then received text that was
# not JSON and mailed "Failing checks: see payload" with the real reason buried. Cron also
# redirects `2>&1` into the same file, so both sides have to keep the streams apart.
python3 "$HERE/healthcheck.py" 2> >(tee -a "$LOG" >&2) | tee -a "$LOG"
status=${PIPESTATUS[0]}
exit "$status"
