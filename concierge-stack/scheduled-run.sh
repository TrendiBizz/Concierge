#!/usr/bin/env bash
# Run by launchd, not by hand (though you can):
#   ./concierge-stack/scheduled-run.sh backup
#   ./concierge-stack/scheduled-run.sh restore-test
#
# Runs backup.sh or restore-test.sh, appends what happened to
# ~/Library/Logs/trendi-concierge-backup.log (snapshot lists and counts only, no secrets), and shows a
# macOS notification if it fails, so a broken backup is not silent.
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$HOME/Library/Logs/trendi-concierge-backup.log"
# launchd starts with a minimal PATH; restic is installed by Homebrew.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$(dirname "$LOG")"

TASK="${1:-backup}"
case "$TASK" in
  backup)       SCRIPT="$DIR/backup.sh" ;;
  restore-test) SCRIPT="$DIR/restore-test.sh" ;;
  *) echo "Usage: $0 backup|restore-test" >&2; exit 2 ;;
esac

stamp() { date '+%Y-%m-%d %H:%M:%S %Z'; }
echo "=== $(stamp) $TASK started" >> "$LOG"
if "$SCRIPT" >> "$LOG" 2>&1; then
  echo "=== $(stamp) $TASK OK" >> "$LOG"
else
  rc=$?
  echo "=== $(stamp) $TASK FAILED (exit $rc)" >> "$LOG"
  osascript -e "display notification \"The scheduled $TASK failed. See ~/Library/Logs/trendi-concierge-backup.log\" with title \"Trendi backup\"" >/dev/null 2>&1 || true
  exit "$rc"
fi
