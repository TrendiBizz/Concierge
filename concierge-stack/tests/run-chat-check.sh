#!/usr/bin/env bash
# Scripted conversation check with a Grok text model. Usage:
#   ./concierge-stack/tests/run-chat-check.sh                 # all scenarios
#   ./concierge-stack/tests/run-chat-check.sh "pen testing"   # one scenario
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$DIR/.env" ]]; then echo "Run set-key.sh first." >&2; exit 1; fi
set -a
# shellcheck disable=SC1091
source "$DIR/.env"
set +a
exec "$DIR/.venv/bin/python" "$DIR/tests/chat_check.py" "$@"
