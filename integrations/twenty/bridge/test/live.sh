#!/usr/bin/env bash
# Real end-to-end check against a running Twenty: a lead posted to the bridge must appear in Twenty.
# Needs an API key in bridge/.twenty-key (Twenty: Settings > APIs & Webhooks > create key).
set -uo pipefail
cd "$(dirname "$0")/.."
KEYFILE="${TWENTY_API_KEY_FILE:-.twenty-key}"
TW="${TWENTY_URL:-http://127.0.0.1:3010}"
PORT="${LIVE_PORT:-4419}"
# Key sources, in order: TWENTY_API_KEY env, the key file, the macOS keychain item concierge-twenty-api-key.
if [ -n "${TWENTY_API_KEY:-}" ]; then KEY="$TWENTY_API_KEY"
elif [ -s "$KEYFILE" ]; then KEY="$(tr -d '[:space:]' < "$KEYFILE")"
else KEY="$(security find-generic-password -s concierge-twenty-api-key -w 2>/dev/null | tr -d '[:space:]')"; fi
[ -n "$KEY" ] || { echo "FAIL: no Twenty API key (env, $KEYFILE, or keychain item concierge-twenty-api-key)."; exit 2; }

PORT="$PORT" TWENTY_URL="$TW" TWENTY_API_KEY="$KEY" node server.js > "${TMPDIR:-/tmp}/bridge-live.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
for i in $(seq 1 20); do curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 0.3; done

EMAIL="live-test-$(date +%s)@example.test"
LEAD="{\"first_name\":\"Live\",\"last_name\":\"Test\",\"email\":\"$EMAIL\",\"phone\":\"021 555 0199\",\"message\":\"Live check from test/live.sh\",\"plan\":\"Starter\"}"
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1 (expected '$3', got '$2')"; fail=$((fail+1)); fi; }
jget() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

R1="$(curl -s -m 20 -X POST "http://127.0.0.1:$PORT/lead" -H 'content-type: application/json' -d "$LEAD")"
echo "first post:  $R1"
check "first lead accepted" "$(echo "$R1" | jget "d.get('ok')")" "True"
check "first lead is new" "$(echo "$R1" | jget "d.get('duplicate')")" "False"
ID="$(echo "$R1" | jget "d.get('twenty_id') or ''")"

R2="$(curl -s -m 20 -X POST "http://127.0.0.1:$PORT/lead" -H 'content-type: application/json' -d "$LEAD")"
echo "second post: $R2"
check "second lead detected as duplicate" "$(echo "$R2" | jget "d.get('duplicate')")" "True"

Q="$(curl -s -m 20 -G "$TW/rest/people" -H "Authorization: Bearer $KEY" --data-urlencode "filter=emails.primaryEmail[eq]:\"$EMAIL\"")"
check "exactly one matching person in Twenty" "$(echo "$Q" | jget "len(d['data']['people'])")" "1"
check "note was attached" "$(echo "$R1" | jget "d.get('note')")" "True"

[ -n "$ID" ] && curl -s -m 20 -X DELETE "$TW/rest/people/$ID" -H "Authorization: Bearer $KEY" >/dev/null && echo "(cleaned up test person $ID)"
echo "result: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
