#!/usr/bin/env bash
# Trendi SEO / crawl deploy gate.
# Exits 0 only when every check PASSes. Any FAIL → non-zero.
# Usage: seo-gate.sh [BASE_URL]
set -euo pipefail

BASE_URL="${1:-https://trendibizz.com}"
BASE_URL="${BASE_URL%/}"
APEX="https://trendibizz.com"
WWW="https://www.trendibizz.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY_JSON="${ROOT}/website/indexnow-key.json"

PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS + 1)); printf 'PASS  %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL  %s\n' "$*"; }
warn() { WARN=$((WARN + 1)); printf 'WARN  %s\n' "$*"; }

BODY_FILE="$(mktemp)"
HDR_FILE="$(mktemp)"
cleanup() { rm -f "$BODY_FILE" "$HDR_FILE"; }
trap cleanup EXIT

# Sets: STATUS CT XROBOTS LOCATION BODY
fetch() {
  local url="$1"
  STATUS="$(curl -sS -D "$HDR_FILE" -o "$BODY_FILE" -w '%{http_code}' --max-time 30 "$url" 2>/dev/null || echo "000")"
  CT="$(awk -F': ' 'BEGIN{IGNORECASE=1} tolower($1)=="content-type"{gsub(/\r/,"",$2); print $2; exit}' "$HDR_FILE" 2>/dev/null || true)"
  XROBOTS="$(awk -F': ' 'BEGIN{IGNORECASE=1} tolower($1)=="x-robots-tag"{gsub(/\r/,"",$2); print $2; exit}' "$HDR_FILE" 2>/dev/null || true)"
  LOCATION="$(awk -F': ' 'BEGIN{IGNORECASE=1} tolower($1)=="location"{gsub(/\r/,"",$2); print $2; exit}' "$HDR_FILE" 2>/dev/null || true)"
  # Text-safe: strip NULs so binary bodies (favicon) do not warn under set -euo
  BODY="$(tr -d '\000' < "$BODY_FILE" 2>/dev/null || true)"
}

printf '=== Trendi SEO gate ===\n'
printf 'BASE_URL=%s\n' "$BASE_URL"
printf 'time=%s (Pacific/Auckland)\n\n' "$(TZ=Pacific/Auckland date '+%Y-%m-%d %H:%M:%S %Z')"

# --- a) Homepage ---
fetch "${BASE_URL}/"
if [[ "$STATUS" == "200" ]]; then
  pass "GET / → 200"
else
  fail "GET / → HTTP $STATUS (want 200)"
fi

if echo "$XROBOTS" | grep -qi 'noindex'; then
  fail "X-Robots-Tag contains noindex: $XROBOTS"
else
  pass "no X-Robots-Tag: noindex on homepage"
fi

# Meta robots: accept name/content attributes in either order.
ROBOTS_CONTENT="$(echo "$BODY" | tr '\n' ' ' | grep -oiE '<meta[^>]*name=["'\'']robots["'\''][^>]*>' \
  | grep -oiE 'content=["'\''][^"'\'']*["'\'']' || true)"
if echo "$ROBOTS_CONTENT" | grep -qi 'noindex'; then
  fail "homepage meta robots contains noindex"
elif echo "$ROBOTS_CONTENT" | grep -qi 'index'; then
  pass "homepage meta robots includes index"
else
  fail "homepage missing meta robots with index"
fi

if echo "$BODY" | grep -qi 'rel="canonical"' && echo "$BODY" | grep -q 'href="https://trendibizz.com/"'; then
  pass "canonical https://trendibizz.com/"
else
  fail "canonical missing or not https://trendibizz.com/"
fi

if echo "$BODY" | grep -qi 'property="og:url"' && echo "$BODY" | grep -q 'content="https://trendibizz.com/"'; then
  pass "og:url https://trendibizz.com/"
else
  fail "og:url missing or not https://trendibizz.com/"
fi

if echo "$BODY" | grep -qE '"@type": "Organization"|"@type":"Organization"'; then
  pass "JSON-LD contains Organization"
else
  fail "JSON-LD missing Organization"
fi

if echo "$BODY" | grep -qE '"@type": "WebSite"|"@type":"WebSite"'; then
  pass "JSON-LD contains WebSite"
else
  fail "JSON-LD missing WebSite"
fi

# --- b) robots.txt ---
fetch "${BASE_URL}/robots.txt"
CT_LOWER="$(echo "$CT" | tr '[:upper:]' '[:lower:]')"
if [[ "$STATUS" == "200" ]]; then
  pass "GET /robots.txt → 200"
else
  fail "GET /robots.txt → HTTP $STATUS (want 200) — this is the 2826a2a8-class failure"
fi
if echo "$CT_LOWER" | grep -q 'text/plain'; then
  pass "robots.txt Content-Type text/plain"
else
  fail "robots.txt Content-Type not text/plain (got: ${CT:-empty})"
fi
if echo "$BODY" | grep -qE '^Allow:'; then
  pass "robots.txt contains Allow"
else
  fail "robots.txt missing Allow"
fi
if echo "$BODY" | grep -qF 'Sitemap: https://trendibizz.com/sitemap.xml'; then
  pass "robots.txt Sitemap: https://trendibizz.com/sitemap.xml"
else
  fail "robots.txt missing Sitemap: https://trendibizz.com/sitemap.xml"
fi

# --- c) IndexNow key file ---
if [[ ! -f "$KEY_JSON" ]]; then
  fail "local website/indexnow-key.json missing"
  KEY=""
else
  KEY="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["key"])' "$KEY_JSON")"
fi
if [[ -n "${KEY:-}" ]]; then
  KEY_PATH="/${KEY}.txt"
  fetch "${BASE_URL}${KEY_PATH}"
  if [[ "$STATUS" == "200" ]]; then
    pass "GET IndexNow key file → 200 (${KEY_PATH})"
  else
    fail "GET IndexNow key file → HTTP $STATUS (want 200)"
  fi
  BODY_TRIM="$(printf '%s' "$BODY" | tr -d '\r\n')"
  if [[ "$BODY_TRIM" == "$KEY" ]]; then
    pass "IndexNow key body equals key exactly"
  else
    fail "IndexNow key body mismatch (got ${#BODY_TRIM} chars)"
  fi
fi

# --- d) llms.txt ---
fetch "${BASE_URL}/llms.txt"
CT_LOWER="$(echo "$CT" | tr '[:upper:]' '[:lower:]')"
if [[ "$STATUS" == "200" ]]; then
  pass "GET /llms.txt → 200"
else
  fail "GET /llms.txt → HTTP $STATUS"
fi
if echo "$CT_LOWER" | grep -q 'text/plain'; then
  pass "llms.txt Content-Type text/plain"
else
  fail "llms.txt Content-Type not text/plain (got: ${CT:-empty})"
fi

# --- e) sitemap.xml ---
fetch "${BASE_URL}/sitemap.xml"
if [[ "$STATUS" == "200" ]]; then
  pass "GET /sitemap.xml → 200"
else
  fail "GET /sitemap.xml → HTTP $STATUS"
fi
if echo "$BODY" | grep -qE '<urlset|<sitemapindex'; then
  pass "sitemap.xml well-formed root element"
else
  fail "sitemap.xml missing urlset/sitemapindex"
fi
if echo "$BODY" | grep -qF '<loc>https://trendibizz.com/</loc>'; then
  pass "sitemap contains <loc>https://trendibizz.com/</loc>"
else
  fail "sitemap missing homepage loc"
fi

# --- f) unknown path → 404 ---
fetch "${BASE_URL}/seo-gate-missing-path-$(date +%s)-xyz"
if [[ "$STATUS" == "404" ]]; then
  pass "unknown path → HTTP 404"
else
  fail "unknown path → HTTP $STATUS (want 404, not soft-200 homepage)"
fi

# --- g) www → apex (production only) ---
if [[ "$BASE_URL" == "$APEX" || "$BASE_URL" == "$WWW" ]]; then
  fetch "${WWW}/"
  if [[ "$STATUS" == "301" || "$STATUS" == "308" ]]; then
    if [[ "$LOCATION" == "https://trendibizz.com/" || "$LOCATION" == "https://trendibizz.com" ]]; then
      pass "www → apex HTTP $STATUS to https://trendibizz.com/"
    else
      fail "www redirect Location not apex (got: ${LOCATION:-empty})"
    fi
  else
    fail "www → apex want 301/308, got HTTP $STATUS"
  fi
else
  warn "skip www→apex (BASE_URL is not production apex/www)"
fi

# --- h) favicon.ico ---
fetch "${BASE_URL}/favicon.ico"
if [[ "$STATUS" == "200" ]]; then
  pass "GET /favicon.ico → 200"
else
  fail "GET /favicon.ico → HTTP $STATUS (want 200)"
fi

printf '\n=== SUMMARY ===\n'
printf 'PASS=%s FAIL=%s WARN=%s\n' "$PASS" "$FAIL" "$WARN"
if [[ "$FAIL" -gt 0 ]]; then
  printf 'GATE RESULT: FAIL — do not treat this deploy as successful\n'
  exit 1
fi
printf 'GATE RESULT: PASS\n'
exit 0
