#!/usr/bin/env bash
# Deploy the Studio portal without a window where customers see "Internal Server Error".
#
# Why this exists (2026-11-14): the portal used to be rsynced straight into the live directory
# with `-a`, which preserves the source's permissions as files land, and the follow-up `chmod -R
# a+rX` only ran *after* the whole copy finished. For the length of that window index.html was a
# regular file the API user could not read; the /studio route raised PermissionError and every
# visitor got a bare 500. Eight were logged during one deploy.
#
# This script copies into staging first, fixes permissions there, then swaps the tree into place
# and verifies the page actually serves before reporting success.
#
# usage: KEY=./Concierge ./scripts/vps/deploy-studio.sh [dist-dir]
#   HOST (default root@152.42.239.240), DEST (default /opt/trendi/shared/studio)
set -euo pipefail

HOST="${HOST:-root@152.42.239.240}"
DEST="${DEST:-/opt/trendi/shared/studio}"
KEY="${KEY:-./Concierge}"
DIST="${1:-web/portal/dist}"
URL="${URL:-https://concierge.trendibizz.com/studio}"

[ -f "$DIST/index.html" ] || { echo "no built portal at $DIST/index.html — run pnpm run build" >&2; exit 1; }

SSH="ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY $HOST"
RSSH="rsync -a --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r --delay-updates --delete-delay -e 'ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY'"

echo "==> stamping the service-worker cache name with this build"
# The worker's cache is named after the build, so a new build starts from an empty cache instead of
# serving yesterday's shell. Without this the name never changes and stale clients never recover.
BUILD_ID=$(grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$DIST/index.html" | head -1 | sed 's#assets/index-##;s#\.js##')
[ -n "$BUILD_ID" ] || { echo "could not read the build id from $DIST/index.html" >&2; exit 1; }
sed -i.bak "s/__BUILD__/$BUILD_ID/" "$DIST/sw-v2.js" && rm -f "$DIST/sw-v2.js.bak"
echo "    build $BUILD_ID"

echo "==> staging $DIST to $DEST.staging"
$SSH "rm -rf $DEST.staging && mkdir -p $DEST.staging"
eval $RSSH "$DIST/" "$HOST:$DEST.staging/"

echo "==> permissions in staging, before anything goes live"
$SSH "chmod -R a+rX $DEST.staging"

echo "==> swapping staging into place"
# rsync from staging into the live tree: every file lands world-readable, deletions are deferred
# to the end so a browser mid-session does not lose an asset it is about to fetch.
$SSH "rsync -a --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r --delay-updates --delete-delay $DEST.staging/ $DEST/ \
      && chmod -R a+rX $DEST && rm -rf $DEST.staging"

echo "==> verifying the page serves"
for attempt in 1 2 3; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0 (deploy check)' "$URL")
  if [ "$code" = "200" ]; then
    echo "==> /studio 200 (attempt $attempt)"
    if [ "$attempt" -eq 3 ]; then echo "==> done"; exit 0; fi
  else
    echo "!!! /studio returned $code" >&2
    [ "$attempt" -eq 3 ] && { echo "deploy FAILED: the page does not serve" >&2; exit 1; }
    sleep 2
  fi
done
