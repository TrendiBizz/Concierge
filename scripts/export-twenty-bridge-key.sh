#!/usr/bin/env bash
# Prepare a Docker secret from the existing Mac Keychain without echoing it.
# Does NOT start containers or expose the bridge to the network.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$DIR/.private/twenty-api-key"
AUTH="$DIR/.private/twenty-bridge-auth"
umask 077
mkdir -p "$DIR/.private"
chmod 700 "$DIR/.private"
if [[ -e "$DEST" || -e "$AUTH" ]]; then
  echo "A private bridge secret already exists; refusing to replace it." >&2
  exit 1
fi
TEMP="$(mktemp "$DIR/.private/.key.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT
chmod 600 "$TEMP"
security find-generic-password -s concierge-twenty-api-key -w > "$TEMP"
[[ -s "$TEMP" ]] || { echo "Keychain item empty or unavailable" >&2; exit 1; }
AUTH_TEMP="$(mktemp "$DIR/.private/.auth.XXXXXX")"
trap 'rm -f "$TEMP" "$AUTH_TEMP"' EXIT
chmod 600 "$AUTH_TEMP"
openssl rand -hex 32 > "$AUTH_TEMP"
mv "$TEMP" "$DEST"
mv "$AUTH_TEMP" "$AUTH"
trap - EXIT
echo "Private Docker bridge credentials prepared under .private/ (contents not shown)."
echo "No containers were started."
