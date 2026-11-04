#!/usr/bin/env bash
# Start everything: LM Studio server -> load the model -> Docker -> the concierge stack.
# Idempotent: anything already running is left alone. Safe to run at login (see
# scripts/install-autostart-macos.sh).
set -euo pipefail

cd "$(dirname "$0")/.."
# launchd gives agents a minimal PATH, so add the usual locations.
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[ -f .env ] || die ".env not found. Run scripts/gen-env.sh, then scripts/configure-lmstudio.sh"
get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

PORT="$(get LMSTUDIO_PORT)";          PORT="${PORT:-1234}"
IDENT="$(get LMSTUDIO_IDENTIFIER)";   IDENT="${IDENT:-$(get CHAT_MODEL)}"; IDENT="${IDENT:-concierge}"
MODEL_PATH="$(get LMSTUDIO_MODEL_PATH)"
CTX="$(get LMSTUDIO_CONTEXT)";        CTX="${CTX:-8192}"
GPU="$(get LMSTUDIO_GPU)";            GPU="${GPU:-max}"
API_KEY="$(get LLM_API_KEY)"
LM_URL="http://127.0.0.1:${PORT}/v1/models"

# True once the URL answers with a 2xx. Sends the API key in case LM Studio requires one.
wait_for() {
  local url="$1" limit="$2" waited=0
  until curl -fsS -o /dev/null --max-time 3 -H "Authorization: Bearer ${API_KEY:-none}" "$url" 2>/dev/null; do
    waited=$((waited + 3))
    [ "$waited" -ge "$limit" ] && return 1
    sleep 3
  done
}

# ---- 1. Docker ----------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  if [ "$(uname)" = "Darwin" ]; then
    log "Starting Docker Desktop..."
    open -a Docker || true
  fi
  for _ in $(seq 1 60); do
    docker info >/dev/null 2>&1 && break
    sleep 3
  done
  docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop and re-run."
fi
log "Docker is running"

# ---- 2. LM Studio server --------------------------------------------------------
command -v lms >/dev/null 2>&1 || die "The 'lms' CLI was not found. Install it from LM Studio (see https://lmstudio.ai/docs/lms)."

if wait_for "$LM_URL" 3; then
  log "LM Studio server already running on port ${PORT}"
else
  log "Starting LM Studio server on port ${PORT}..."
  start_server() { if [ "$PORT" = "1234" ]; then lms server start; else lms server start --port "$PORT"; fi; }
  if ! start_server; then
    # The CLI may need the LM Studio app/daemon running first.
    if [ "$(uname)" = "Darwin" ]; then
      log "Opening the LM Studio app and retrying..."
      open -a "LM Studio" || true
      sleep 15
    fi
    start_server || die "Could not start the LM Studio server. Open LM Studio, Developer tab, and start it."
  fi
  wait_for "$LM_URL" 60 || die "LM Studio server did not come up on ${LM_URL}"
fi

# ---- 3. Load the model -------------------------------------------------------------
if lms ps 2>/dev/null | grep -qF "$IDENT"; then
  log "Model '${IDENT}' is already loaded"
else
  if [ -z "$MODEL_PATH" ]; then
    lms ls || true
    die "LMSTUDIO_MODEL_PATH is empty. Pick a path from the list above and run scripts/configure-lmstudio.sh \"<path>\""
  fi
  log "Loading model '${MODEL_PATH}' as '${IDENT}' (gpu=${GPU}, context=${CTX})..."
  lms load "$MODEL_PATH" --identifier="$IDENT" --gpu="$GPU" --context-length="$CTX" -y \
    || die "lms load failed. Check the model path with 'lms ls' and the flags with 'lms load --help'."
fi

if ! curl -fsS --max-time 5 -H "Authorization: Bearer ${API_KEY:-none}" "$LM_URL" 2>/dev/null | grep -qF "$IDENT"; then
  log "WARNING: model id '${IDENT}' was not listed by ${LM_URL}; check CHAT_MODEL matches 'lms ps'."
fi

# ---- 4. The concierge stack --------------------------------------------------------
log "Starting the concierge (docker compose up)..."
docker compose up -d --build

if wait_for "http://127.0.0.1:8000/healthz" 300; then
  log "Concierge is up."
  log "  Dashboard:  http://127.0.0.1:8000/admin-ui"
  log "  API docs:   http://127.0.0.1:8000/docs"
  log "  Text model: ${IDENT} on LM Studio (port ${PORT})"
else
  die "The API did not become healthy in time. See: docker compose logs api"
fi
