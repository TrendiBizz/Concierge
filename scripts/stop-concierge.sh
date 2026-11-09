#!/usr/bin/env bash
# Stop the concierge stack and free LM Studio's memory.
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

log "Stopping the concierge stack..."
docker compose down || log "docker compose down failed (is Docker running?)"

if command -v lms >/dev/null 2>&1; then
  log "Unloading models and stopping the LM Studio server..."
  lms unload --all || true
  lms server stop || true
fi
log "Stopped. Your data is kept in Docker volumes."
