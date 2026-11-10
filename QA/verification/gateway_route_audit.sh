#!/usr/bin/env bash
# Audit that every route the API serves is reachable through the gateway.
#
# Why this exists: a gateway whose path list is narrower than the application silently blocks
# features. That happened once -- /api/v1/phone/managed/* was served by the API but absent from the
# gateway's owner route, so the carrier webhook returned 404 at the edge while working at origin, and
# would have looked like a broken integration with the API appearing correct.
#
# A 404 at the edge means the gateway refused the path. Any other status (401, 403, 405, 422, 429,
# 500, 503) means the request reached the application, which is what this checks.
#
# Usage: ./gateway_route_audit.sh [portal_url] [chat_url]
set -uo pipefail
BASE="${1:-https://concierge.trendibizz.com}"
CHAT="${2:-https://chat.trendibizz.com}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

if ! routes=$(python3 "$HERE/gateway_route_list.py" "$REPO"); then
  echo "could not build the route list" >&2
  exit 2
fi

checked=0
blocked=""
while read -r route; do
  [ -n "$route" ] || continue
  path=$(printf '%s' "$route" | sed 's/{[^}]*}/1/g')
  # The gateway routes by host: chat-facing paths live on the chat host, the rest on the portal host.
  # Probing the wrong host yields a 404 that is a routing decision, not a blocked feature.
  case "$path" in
    /api/v1/chat|/api/v1/voice/token|/api/v1/voice/log|/api/v1/widget-config|\
    /api/v1/tools/*|/api/v1/unsubscribe/*|/api/v1/sms/*|/api/v1/smsgate/*|\
    /api/v1/voice/sessions/*) host="$CHAT" ;;
    *) host="$BASE" ;;
  esac
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -A 'Mozilla/5.0' -X POST "$host$path")
  checked=$((checked + 1))
  if [ "$code" = "404" ]; then
    blocked="$blocked
  $route -> 404"
  fi
done <<< "$routes"

echo "checked $checked routes across $BASE and $CHAT"
if [ -n "$blocked" ]; then
  echo "BLOCKED AT THE EDGE (gateway refuses a path the app serves):$blocked"
  exit 1
fi
echo "OK: every app route reaches the application (no 404 at the edge)"
