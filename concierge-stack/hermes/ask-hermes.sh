#!/usr/bin/env bash
# Ask the local Hermes one question and print the answer. Prints no keys.
#   ./concierge-stack/hermes/ask-hermes.sh "Say hello in five words"
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS="$DIR/hermes.env"
if [[ ! -f "$SECRETS" ]]; then echo "Run ./concierge-stack/hermes/start-hermes.sh first." >&2; exit 1; fi
if [[ $# -lt 1 ]]; then echo "Usage: $0 \"your question\"" >&2; exit 1; fi

HERMES_KEY="$(grep '^HERMES_API_KEY=' "$SECRETS" | head -1 | cut -d= -f2-)"
PROMPT="$1"
export PROMPT

BODY="$(python3 -c 'import json,os; print(json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":os.environ["PROMPT"]}]}))')"

RESPONSE="$(curl -sS -m 120 "http://127.0.0.1:8642/v1/chat/completions" \
  -H "Authorization: Bearer $HERMES_KEY" -H "Content-Type: application/json" -d "$BODY")" || {
  echo "Could not reach Hermes. Is it running?" >&2; exit 1; }

printf '%s' "$RESPONSE" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    print(data["choices"][0]["message"]["content"])
except Exception:
    print("Unexpected reply (first 400 characters):")
    print(raw[:400])
    sys.exit(1)
'
