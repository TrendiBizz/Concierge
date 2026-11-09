#!/usr/bin/env bash
# Start the lead bridge, reading the Twenty API key from the macOS keychain (item concierge-twenty-api-key).
# HOST=0.0.0.0 ./start.sh   lets a VM or another machine reach it.
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${TWENTY_API_KEY:-}" ] && [ ! -s "${TWENTY_API_KEY_FILE:-.twenty-key}" ]; then
  TWENTY_API_KEY="$(security find-generic-password -s concierge-twenty-api-key -w 2>/dev/null | tr -d '[:space:]')" || true
  export TWENTY_API_KEY
fi
exec node server.js
