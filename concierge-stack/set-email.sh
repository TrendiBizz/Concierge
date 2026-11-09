#!/usr/bin/env bash
# Store your Brevo SMTP settings safely. The SMTP key is typed hidden, saved only to
# concierge-stack/.env (git-ignored, owner-only permissions) and never printed, logged or committed.
# Run from a normal Terminal window:  ./concierge-stack/set-email.sh
#
# Where to find the values in Brevo (Settings > SMTP & API > SMTP tab):
#   SMTP server : smtp-relay.brevo.com   Port: 587
#   Login       : the SMTP login shown on that page (looks like 1234abc@smtp-brevo.com)
#   Password    : an SMTP key you generate on that page (NOT the API key)
# The From address must be a sender or domain you have verified in Brevo
# (Settings > Senders, domains & dedicated IPs). Add SPF, DKIM and DMARC for the domain.
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

read -r -p "Brevo SMTP login (e.g. 1234abc@smtp-brevo.com): " LOGIN
if [[ -z "${LOGIN// }" ]]; then
  echo "No login entered. Nothing changed." >&2
  exit 1
fi

read -r -s -p "Brevo SMTP key (hidden), then press Return: " KEY
echo
if [[ -z "${KEY// }" ]]; then
  echo "No key entered. Nothing changed." >&2
  exit 1
fi

read -r -p "From address, verified in Brevo (e.g. bookings@trendibizz.com): " FROM
if [[ -z "${FROM// }" ]]; then
  echo "No From address entered. Nothing changed." >&2
  exit 1
fi

set_var SMTP_HOST "smtp-relay.brevo.com"
set_var SMTP_PORT "587"
set_var SMTP_USER "$LOGIN"
set_var SMTP_PASSWORD "$KEY"
set_var EMAIL_FROM "$FROM"
unset KEY

echo "Saved Brevo settings to $ENV_FILE (owner-only, git-ignored)."
echo "Next: ./concierge-stack/tests/send-test-email.sh you@example.com"
