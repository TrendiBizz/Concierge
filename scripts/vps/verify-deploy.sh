#!/usr/bin/env bash
# Prove that what is in the repo is what is actually running on the box.
#
# Why this exists: on 2026-11-15 two drifts were found only by hand — the deployed healthcheck was
# newer than the repo (a fix applied on the box never came back), and the deployed website was
# newer than the local mirror (another deploy landed between sessions). Neither was visible from a
# green health check, because a deployed file that differs from the repo usually still works.
#
# Usage:  KEY=./Concierge ./scripts/vps/verify-deploy.sh
# Exit:   0 when every compared file matches, 1 when anything differs or is missing.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
# The site is compared against the repo's own website/ folder, the same tree deploy-site.sh ships.
# The old default was the retired loose copy /Users/jo/work-staging/trendibizz-live/site, which no
# longer matches production, so parity failed on every deploy (Omega Boss, 2026-11-20).
SITE_MIRROR="${SITE_MIRROR:-${SITE_SRC:-$REPO_ROOT/website}}"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
drift=0

compare() { # local_dir remote_dir label
  local local_dir="$1" remote_dir="$2" label="$3"
  [ -d "$local_dir" ] || return 0
  local remote_list local_list
  # Normalise both sides to "<md5> <path>": md5sum prints two spaces, macOS md5 -r prints one, and
  # macOS leaves AppleDouble ._ files in synced directories. Without this every file looks different
  # and the check reports drift that does not exist (found on the first run, 2026-11-15).
  remote_list="$("${SSH[@]}" "$HOST" "cd '$remote_dir' 2>/dev/null && find . -type f ! -name '._*' \( -name '*.py' -o -name '*.sql' -o -name '*.sh' -o -name '*.html' -o -name '*.xml' -o -name '*.css' -o -name '*.js' -o -name '*.mjs' -o -name 'Caddyfile' -o -name 'compose.yml' -o -name 'Containerfile.*' -o -name '_headers' -o -name 'robots.txt' \) -exec md5sum {} + | sed 's/ \+/ /' | LC_ALL=C sort -k2" 2>/dev/null)"
  if [ -z "$remote_list" ]; then
    echo "  $label: remote directory unreadable ($remote_dir)"; drift=1; return
  fi
  # md5sum on Linux, md5 -r on macOS: both are normalised to "<md5> <path>" by the sed below.
  local hasher="md5 -r"; command -v md5sum >/dev/null 2>&1 && hasher="md5sum"
  local_list="$(cd "$local_dir" && find . -type f ! -name '._*' \( -name '*.py' -o -name '*.sql' -o -name '*.sh' -o -name '*.html' -o -name '*.xml' -o -name '*.css' -o -name '*.js' -o -name '*.mjs' -o -name 'Caddyfile' -o -name 'compose.yml' -o -name 'Containerfile.*' -o -name '_headers' -o -name 'robots.txt' \) -exec $hasher {} + 2>/dev/null | sed 's/  */ /' | LC_ALL=C sort -k2)"
  local diffout
  diffout="$(diff <(echo "$local_list") <(echo "$remote_list"))"
  if [ -n "$diffout" ]; then
    echo "  $label: DRIFT"; echo "$diffout" | sed -n '1,12p' | sed 's/^/    /'; drift=1
  else
    echo "  $label: matches ($(echo "$local_list" | wc -l | tr -d ' ') files)"
  fi
}

# Drift guard (2026-11-24): the website container must not serve any /api/* route. Those belong to the FastAPI
# app in git. Until now site-check, security-check and robots were answered by /website/deploy_known_good/
# _worker.js, a file that is not in git, so they could vanish or change without any repo change or test noticing.
# We ask the RUNNING container (not just the files) about every /api path a page calls, every /api path written
# in the untracked worker file (read only, never changed or deleted) and one canary: all must answer 404.
api_drift_guard() {
  local paths remote_paths all canary="/api/drift-canary-$$" bad=0 probed=0 want line code
  paths="$(python3 "$REPO_ROOT/scripts/verify/check_page_api_contract.py" "$REPO_ROOT" --paths 2>/dev/null)"
  [ -n "$paths" ] || { echo "  api drift guard: could not list the /api paths the pages call"; drift=1; return; }
  remote_paths="$("${SSH[@]}" -n "$HOST" "grep -ao '/api/[A-Za-z0-9_/-]*' '$RELEASE/website/deploy_known_good/_worker.js' 2>/dev/null | sort -u")"
  all="$(printf '%s\n%s\n%s\n' "$paths" "$remote_paths" "$canary" | grep . | sort -u)"
  want="$(printf '%s\n' "$all" | grep -c .)"
  while IFS= read -r line; do
    # ssh -n: without it ssh reads the rest of this loop's input and only the first path is ever probed.
    code="$("${SSH[@]}" -n "$HOST" "podman exec trendi-website-1 wget -S -O /dev/null --timeout=5 'http://127.0.0.1:8080$line' 2>&1 | awk '/HTTP\\//{print \$2; exit}'")"
    probed=$((probed + 1))
    if [ "$code" != "404" ]; then
      echo "  api drift guard: the website container answers $line with HTTP ${code:-none}; it is served from a file not in git (deploy_known_good/_worker.js). Serve it from api/ and route it in the Caddyfile."
      bad=1
    fi
  done <<< "$all"
  if [ "$probed" -ne "$want" ]; then
    echo "  api drift guard: probed $probed of $want paths; the guard itself is broken"; bad=1
  fi
  if [ "$bad" -eq 0 ]; then
    echo "  api drift guard: the website container serves no /api/* route (probed all $probed paths, including the worker file's own list and a canary)"
  else
    drift=1
  fi
}

# Post-deploy smoke: every public tool endpoint, live, against the safe target trendibizz.com. Wrong status,
# wrong content type, an answer that did not come from the git-tracked API, or a missing route => non-zero.
tool_smoke() {
  echo "  tool smoke against ${SMOKE_BASE:-https://trendibizz.com}"
  if python3 "$REPO_ROOT/scripts/vps/tool_endpoints.py" --base "${SMOKE_BASE:-https://trendibizz.com}" --functional | sed 's/^/    /'; [ "${PIPESTATUS[0]}" -eq 0 ]; then
    :
  else
    drift=1
  fi
}

echo "verify-deploy against $HOST"
compare "$REPO_ROOT/api/app"            "$RELEASE/product/api/app"              "api/app"
compare "$REPO_ROOT/api/static"         "$RELEASE/product/api/static"           "api/static"
compare "$REPO_ROOT/api/migrations"     "$RELEASE/product/api/migrations"       "api/migrations"
compare "$REPO_ROOT/scripts/vps"        "$RELEASE/product/scripts/vps"           "scripts/vps"
compare "$SITE_MIRROR"                  "$RELEASE/website/site"                  "website/site"
api_drift_guard
tool_smoke
if [ "$drift" -eq 0 ]; then echo "OK: repo and box agree"; else echo "FAIL: drift above"; fi
exit "$drift"
