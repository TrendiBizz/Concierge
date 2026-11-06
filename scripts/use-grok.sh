#!/usr/bin/env bash
# Switch the Concierge chat from the local LM Studio model to xAI Grok.
#
#   1. Copy your xAI API key to the clipboard (from the xAI console).
#   2. ./scripts/use-grok.sh --from-clipboard      (first time: stores the key in the login keychain)
#      ./scripts/use-grok.sh                       (later: uses the key already in the keychain)
#   Go back to the local model:  ./scripts/use-grok.sh --rollback
#
# Model: grok-4.7 by default; override with GROK_MODEL=grok-4.3 ./scripts/use-grok.sh
# The key lives in the keychain item "xai-api-key" and is written to ~/Concierge/.env (which is gitignored,
# like the other keys there). It is never printed. The old .env is saved as .env.bak-before-grok.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${GROK_MODEL:-grok-4.7}"
ENVF=".env"
BAK=".env.bak-before-grok"

if [ "${1:-}" = "--rollback" ]; then
  [ -f "$BAK" ] || { echo "No backup $BAK to roll back to." >&2; exit 1; }
  cp "$BAK" "$ENVF"
  docker compose up -d api
  echo "Rolled back to the settings saved before the Grok switch."
  exit 0
fi

if [ "${1:-}" = "--from-clipboard" ]; then
  K="$(pbpaste | tr -d '[:space:]')"
  [ -n "$K" ] || { echo "Clipboard is empty." >&2; exit 1; }
  case "$K" in
    xai-*) ;;
    *) echo "The clipboard does not look like an xAI key (xAI keys start with xai-). Copy the key from the xAI console, then run this again. Nothing was stored." >&2; exit 1 ;;
  esac
  # stdin, so the key does not appear in the process list
  printf 'add-generic-password -U -a "xai" -s "xai-api-key" -l "xAI API key (Grok)" -w "%s"\n' "$K" | security -i
  unset K
  echo "Stored the key in keychain item xai-api-key."
fi

KEY="$(security find-generic-password -s xai-api-key -w 2>/dev/null | tr -d '[:space:]')" \
  || { echo "No keychain item xai-api-key. Copy the key and run with --from-clipboard." >&2; exit 1; }
[ -n "$KEY" ] || { echo "Empty key." >&2; exit 1; }

# 1) prove the key works and the model exists before touching anything
code="$(curl -s -m20 -o /tmp/grok-models.json -w '%{http_code}' https://api.x.ai/v1/models -H "Authorization: Bearer $KEY")"
if [ "$code" != "200" ]; then echo "xAI rejected the key (HTTP $code). Nothing changed." >&2; exit 1; fi
if ! grep -q "\"$MODEL\"" /tmp/grok-models.json; then
  echo "Model '$MODEL' is not in your xAI model list. Models available:" >&2
  python3 -c 'import json; print(", ".join(sorted(m["id"] for m in json.load(open("/tmp/grok-models.json"))["data"])))' >&2
  echo "Nothing changed. Re-run with GROK_MODEL=<one of those>." >&2
  exit 1
fi
rm -f /tmp/grok-models.json

# 2) update .env (backup first); the key goes in via the environment, not the command line
[ -f "$BAK" ] || cp "$ENVF" "$BAK"
GROK_KEY="$KEY" GROK_MODEL_NAME="$MODEL" python3 - <<'PY'
import os, re
p = ".env"
s = open(p).read()
vals = {
    "LLM_BASE_URL": "https://api.x.ai/v1",
    "LLM_API_KEY": os.environ["GROK_KEY"],
    "CHAT_MODEL": os.environ["GROK_MODEL_NAME"],
}
for k, v in vals.items():
    if re.search(rf"^{k}=.*$", s, flags=re.M):
        s = re.sub(rf"^{k}=.*$", lambda m, k=k, v=v: f"{k}={v}", s, flags=re.M)
    else:
        s += f"\n{k}={v}\n"
open(p, "w").write(s)
PY
unset KEY GROK_KEY

# 3) restart only the API container
docker compose up -d api
for i in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' concierge-api-1 2>/dev/null)" = healthy ] && break
  sleep 2
done
echo "API restarted on model $MODEL."
echo "Test it with a real question, for example:"
echo "  curl -s -X POST http://127.0.0.1:8000/api/v1/chat -H 'content-type: application/json' \\"
echo "    -d '{\"key\":\"<tenant public key>\",\"session_id\":\"grok-test-1\",\"message\":\"What does Concierge do?\"}'"
