#!/bin/bash
# Reads the read-only token from the macOS Keychain straight into this process env. Never printed or logged.
# The Keychain item is the watch's source of truth; ~/.config/trendi/cloudflare_token is only a copy.
# Usage: bash run-snapshot.sh [out.json]   (default ~/.workwatch/tamper-snapshot.json)
set -euo pipefail
OUT="${1:-$HOME/.workwatch/tamper-snapshot.json}"
# Resolve a relative output path against the caller's directory before cd.
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
cd "$(dirname "$0")"
mkdir -p "$(dirname "$OUT")"
# macOS: Keychain. Container (no `security` CLI): the mounted 0600 copy.
if command -v security >/dev/null 2>&1; then
  TOKEN="$(security find-generic-password -s trendi-cf-readonly-token -w)"
else
  TOKEN="$(cat "${CF_TOKEN_FILE:-$HOME/.config/trendi/cloudflare_token}")"
fi
NODE="${NODE_BIN:-$(command -v node || echo /opt/homebrew/opt/node@24/bin/node)}"
CF_READONLY_TOKEN="$TOKEN" "$NODE" cf-run-snapshot.js "$OUT"
