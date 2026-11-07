#!/usr/bin/env bash
# Enter your xAI key safely. The key is typed hidden, saved only to concierge-stack/.env
# (git-ignored, owner-only permissions) and never printed, logged or committed.
# Run from a normal Terminal window:  ./concierge-stack/set-key.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$DIR/env.example" "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

# Replace KEY=value in .env (or append it) without echoing the value.
set_var() {
  local name="$1" value="$2" tmp
  tmp="$(mktemp)"
  grep -v "^${name}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$name" "$value" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

read -r -s -p "Paste your xAI API key (hidden), then press Return: " KEY
echo
if [[ -z "${KEY// }" ]]; then
  echo "No key entered. Nothing changed." >&2
  exit 1
fi
set_var XAI_API_KEY "$KEY"

# Generate strong local secrets once, if they are still the placeholders.
if grep -q '^LIVEKIT_API_SECRET=change-me' "$ENV_FILE"; then
  set_var LIVEKIT_API_SECRET "$(openssl rand -hex 24)"
fi

read -r -p "Number a human should answer on transfer (E.164, e.g. +6421XXXXXXX; blank to skip): " NUM
if [[ -n "${NUM// }" ]]; then
  set_var HUMAN_TRANSFER_NUMBER "$NUM"
fi

# Optional check: asks xAI to list models with the key. Only the HTTP status is shown.
read -r -p "Check the key with xAI now? [y/N] " CHK
if [[ "$CHK" =~ ^[Yy]$ ]]; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
    -H "Authorization: Bearer $KEY" https://api.x.ai/v1/models || true)"
  if [[ "$CODE" == "200" ]]; then
    echo "xAI accepted the key (HTTP 200)."
  else
    echo "xAI did not accept the key (HTTP $CODE). Check it and run this again." >&2
  fi
fi
unset KEY
echo "Saved to $ENV_FILE (owner-only, git-ignored)."
