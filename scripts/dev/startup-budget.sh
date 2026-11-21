#!/usr/bin/env bash
# Fail if a file every agent reads at session start grows past its byte budget.
# Usage: scripts/dev/startup-budget.sh   (exit 0 ok, 1 over budget)
# Move history to docs/archive/ instead of raising a budget.
set -u
cd "$(dirname "$0")/../.." || exit 2
rc=0
check() { # file budget
  [ -e "$1" ] || return 0
  n=$(wc -c < "$1" | tr -d ' ')
  if [ "$n" -gt "$2" ]; then echo "OVER  $1: $n > $2 bytes"; rc=1; else echo "ok    $1: $n/$2"; fi
}
check AGENTS.md 4500
check HANDOFF.md 8000
check outputs/SESSION_HANDOFF_LATEST.md 4500
check outputs/.session_notes.md 2500
check docs/AGENT_WORKING_ORDER.md 6000
exit $rc
