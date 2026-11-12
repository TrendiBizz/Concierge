#!/usr/bin/env bash
# Wrapper for healthcheck.py: run it from cron every five minutes.
#
#   */5 * * * * /opt/trendi/releases/20261108-vps/product/scripts/vps/healthcheck.sh
#
# Exit 0 = healthy. Exit 1 = at least one failing check (so cron also mails root).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /opt/trendi/monitoring

exec python3 "$HERE/healthcheck.py" 2>&1 | tee -a /opt/trendi/monitoring/health.log
