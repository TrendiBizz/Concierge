#!/bin/bash
# Double-click in Finder to stop the concierge and unload LM Studio.
cd "$(dirname "$0")" || exit 1
./scripts/stop-concierge.sh
read -r -p "Press Enter to close..." _
