#!/usr/bin/env bash
# Run the Grok Voice concierge on this Mac, talking through the Mac microphone and speakers.
# No server, Docker or phone number needed. Usage:
#   ./concierge-stack/run-local.sh            # talk to the agent in the terminal (console mode)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/.env"
VENV="$DIR/.venv"

if [[ ! -f "$ENV_FILE" ]] || ! grep -q '^XAI_API_KEY=.\+' "$ENV_FILE"; then
  echo "No xAI key yet. Run ./concierge-stack/set-key.sh first." >&2
  exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  PY="$(command -v python3.12 || command -v python3.13 || command -v python3.11 || true)"
  if [[ -z "$PY" ]]; then
    echo "Need Python 3.11 to 3.13 (brew install python@3.12)." >&2
    exit 1
  fi
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$DIR/agent/requirements.txt"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Console mode uses your Mac mic and speakers. macOS will ask for microphone permission.
exec "$VENV/bin/python" "$DIR/agent/agent.py" console
