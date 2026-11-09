#!/usr/bin/env bash
# Point the concierge's TEXT chat at a local LM Studio server by editing .env.
# Safe to re-run. Voice still uses xAI Grok (set XAI_API_KEY separately).
#
# Usage:
#   scripts/configure-lmstudio.sh                       # asks which model (needs the `lms` CLI)
#   scripts/configure-lmstudio.sh "<model path>"        # path exactly as shown by `lms ls`
#   scripts/configure-lmstudio.sh "<model path>" mymodel
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.lmstudio/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ ! -f .env ]; then
  ./scripts/gen-env.sh
fi

get_kv() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

# Replace KEY=... in .env, or append it. Values are passed via the environment so that
# characters like & \ / | in a model path cannot break the edit.
set_kv() {
  local tmp
  tmp="$(mktemp)"
  K="$1" V="$2" awk '
    BEGIN { FS = "="; k = ENVIRON["K"]; v = ENVIRON["V"]; done = 0 }
    $1 == k && !done { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }
  ' .env > "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}

MODEL_PATH="${1:-}"
IDENTIFIER="${2:-$(get_kv LMSTUDIO_IDENTIFIER)}"
IDENTIFIER="${IDENTIFIER:-concierge}"

if [ -z "$MODEL_PATH" ]; then
  MODEL_PATH="$(get_kv LMSTUDIO_MODEL_PATH)"
fi
if [ -z "$MODEL_PATH" ] && command -v lms >/dev/null 2>&1 && [ -t 0 ]; then
  echo "Models downloaded in LM Studio:"
  lms ls || true
  echo
  read -r -p "Paste the model path to use (exactly as listed above): " MODEL_PATH
fi

# --- text chat goes to LM Studio (OpenAI-compatible API) -------------------
set_kv LLM_BASE_URL "http://host.docker.internal:1234/v1"
current_key="$(get_kv LLM_API_KEY)"
if [ -z "$current_key" ]; then
  # LM Studio ignores the key unless you enabled authentication; it just must not be empty.
  set_kv LLM_API_KEY "lm-studio"
fi
set_kv CHAT_MODEL "$IDENTIFIER"

# --- settings used by scripts/start-concierge.sh ----------------------------
set_kv LMSTUDIO_MODEL_PATH "$MODEL_PATH"
set_kv LMSTUDIO_IDENTIFIER "$IDENTIFIER"
[ -n "$(get_kv LMSTUDIO_CONTEXT)" ] || set_kv LMSTUDIO_CONTEXT "8192"
[ -n "$(get_kv LMSTUDIO_GPU)" ]     || set_kv LMSTUDIO_GPU "max"
[ -n "$(get_kv LMSTUDIO_PORT)" ]    || set_kv LMSTUDIO_PORT "1234"

chmod 600 .env

echo "Updated .env for LM Studio:"
echo "  LLM_BASE_URL=$(get_kv LLM_BASE_URL)"
echo "  CHAT_MODEL=$(get_kv CHAT_MODEL)"
echo "  LMSTUDIO_MODEL_PATH=$(get_kv LMSTUDIO_MODEL_PATH)"
echo
if [ -z "$(get_kv LMSTUDIO_MODEL_PATH)" ]; then
  echo "NOTE: no model path set yet. Run 'lms ls', then re-run this script with the path,"
  echo "      or put it in .env as LMSTUDIO_MODEL_PATH."
fi
if [ -z "$(get_kv XAI_API_KEY)" ]; then
  echo "NOTE: XAI_API_KEY is empty. Text chat will use LM Studio, but website VOICE needs an xAI key."
fi
echo "If you enabled authentication in LM Studio, put its token in .env as LLM_API_KEY."
