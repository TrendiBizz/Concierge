#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./scripts/start-local.sh
# Keep the secret out of URLs, terminal output and browser history.
pbcopy < .private/local-stack/admin-token.txt
open http://127.0.0.1:8793/admin-ui
echo 'The local admin key is on your clipboard. Paste it into Admin token and sign in.'
