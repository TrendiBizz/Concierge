#!/usr/bin/env bash
# Whole-chain check for inbound email on every tenant.
#
# This exists because the live customer tenant silently refused every inbound message on
# 2026-11-12: it had a reply address, a Cloudflare rule and a Worker route, but no owner
# account and no email_read consent, so the API answered 403 and the mail was only
# forwarded to the operator's inbox. Nothing in the product noticed.
#
# Exit 0 = every tenant's chain is complete. Exit 1 = at least one chain is broken.
# Safe to cron; it only reads.
set -uo pipefail

ENV_FILE="${ENV_FILE:-/opt/trendi/shared/api.env}"
API="${API:-http://127.0.0.1:8000}"

[ -r "$ENV_FILE" ] || { echo "cannot read $ENV_FILE" >&2; exit 2; }
# Read the file as data. Sourcing it ran ASTERISK_CHANNEL_DIAL=PJSIP/<number>@… as a redirect and
# printed "number: No such file or directory" on every cron run (2026-11-15).
# shellcheck source=env_lib.sh
. "$(dirname "$0")/env_lib.sh"
load_env "$ENV_FILE" || { echo "cannot read $ENV_FILE" >&2; exit 2; }
[ -n "${ADMIN_TOKEN:-}" ] || { echo "ADMIN_TOKEN not set in $ENV_FILE" >&2; exit 2; }

response=$(curl -sS -m 30 -w '\n%{http_code}' "$API/admin/inbound-readiness" \
  -H "X-Admin-Token: $ADMIN_TOKEN") || { echo "readiness request failed" >&2; exit 2; }
code=${response##*$'\n'}
json=${response%$'\n'*}
if [ "$code" != "200" ]; then
  echo "readiness returned HTTP $code" >&2
  printf '%s\n' "$json" | head -c 400 >&2
  exit 2
fi

printf '%s' "$json" > /tmp/inbound-readiness.json
exec python3 "$(dirname "$0")/check-inbound-chain.py" /tmp/inbound-readiness.json
