#!/bin/bash
# Reads the read-only token from the macOS Keychain straight into this process env. Never printed or logged.
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-$HOME/.workwatch/tamper-snapshot.json}"
# Resolve a relative output path against the caller's directory before cd.
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
mkdir -p "$(dirname "$OUT")"
CF_READONLY_TOKEN="$(security find-generic-password -s trendi-cf-readonly-token -w)" \
  /opt/homebrew/opt/node@24/bin/node cf-run-snapshot.js "$OUT"
