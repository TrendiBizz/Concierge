#!/bin/bash
# Double-click in Finder to start LM Studio + the concierge (opens in Terminal).
cd "$(dirname "$0")" || exit 1
./scripts/start-concierge.sh
status=$?
echo
[ $status -eq 0 ] && echo "Done. You can close this window." || echo "Something failed (see above)."
read -r -p "Press Enter to close..." _
exit $status
