#!/usr/bin/env bash
# Audit that every API route the app defines is reachable through the gateway.
#
# Why this exists: a gateway whose path list is narrower than the application silently blocks
# features. That happened once -- /api/v1/phone/managed/* was served by the API but absent from the
# gateway's owner route, so the carrier webhook returned 404 at the edge while working at origin, and
# would have looked like a broken integration with the API appearing correct.
#
# A 404 at the edge means the gateway refused the path. Any other status (401, 403, 405, 422, 429,
# 500, 503) means the request reached the application, which is what this checks.
#
# Usage: ./gateway_route_audit.sh [base_url]
set -uo pipefail
BASE="${1:-https://concierge.trendibizz.com}"
CHAT="${2:-https://chat.trendibizz.com}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

routes=$(grep -rhoE '@app\.(get|post|put|patch|delete)\("/api/v1/[^"]+"' "$REPO/api/app/"*.py \
         | sed 's/.*("//; s/"$//' | sort -u)

checked=0; blocked=""
while read -r route; do
  [ -n "$route" ] || continue
  path=$(printf '%s' "$route" | sed 's/{[^}]*}/1/g')
  # The gateway routes by host: chat-facing paths (widget, token, chat, tools, sms) live on the chat
  # host, everything else on the portal host. Probing the wrong host yields a misleading 404 that is
  # a routing decision, not a blocked feature.
  case "$path" in
    /api/v1/chat|/api/v1/voice/token|/api/v1/voice/log|/api/v1/widget-config|    /api/v1/tools/*|/api/v1/unsubscribe/*|/api/v1/sms/*|/api/v1/smsgate/*|    /api/v1/voice/sessions/*) host="$CHAT" ;;
    *) host="$BASE" ;;
  esac
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -A 'Mozilla/5.0' -X POST "$host$path")
  checked=$((checked+1))
  [ "$code" = "404" ] && blocked="$blocked\n  $route -> 404"
done <<< "$routes"

echo "checked $checked /api/v1 routes across $BASE and $CHAT"
if [ -n "$blocked" ]; then
  echo -e "BLOCKED AT THE EDGE (gateway refuses a path the app serves):$blocked"
  exit 1
fi
echo "OK: every app route reaches the application (no 404 at the edge)"
