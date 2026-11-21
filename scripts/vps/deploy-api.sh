#!/usr/bin/env bash
# Deploy the API and its static pages/assets as one unit.
#
# Why this exists (2026-11-16): the documented API deploy only rsynced `api/app/`, but the image
# also copies `api/static` (owner.html, widget.js, and now qrcode.js). A static-only fix could be
# committed, "deployed" and verified while the box kept serving the old page. This copies both,
# rebuilds the image, recreates api + social, then runs the checksum check.
#
# usage: KEY=./Concierge ./scripts/vps/deploy-api.sh   (run sync-tooling.sh first when compose or Containerfiles changed)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
KEY="${KEY:-$REPO_ROOT/Concierge}"
PRODUCT="$RELEASE/product"

SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST")
RSSH=(rsync -a --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r --delay-updates
      -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY")

[ -d "$REPO_ROOT/api/app" ] || { echo "no api/app in $REPO_ROOT" >&2; exit 1; }
[ -d "$REPO_ROOT/api/static" ] || { echo "no api/static in $REPO_ROOT" >&2; exit 1; }
[ -f "$REPO_ROOT/api/alembic.ini" ] || { echo "no api/alembic.ini in $REPO_ROOT" >&2; exit 1; }
[ -d "$REPO_ROOT/api/migrations" ] || { echo "no api/migrations in $REPO_ROOT" >&2; exit 1; }

echo "==> syncing api/app, api/static, api/alembic.ini, and api/migrations to $HOST:$PRODUCT/api"
"${RSSH[@]}" "$REPO_ROOT/api/app/" "$HOST:$PRODUCT/api/app/"
"${RSSH[@]}" "$REPO_ROOT/api/static/" "$HOST:$PRODUCT/api/static/"
"${RSSH[@]}" "$REPO_ROOT/api/alembic.ini" "$HOST:$PRODUCT/api/alembic.ini"
"${RSSH[@]}" "$REPO_ROOT/api/migrations/" "$HOST:$PRODUCT/api/migrations/"

echo "==> moving files removed from the repo aside on the box"
KEY="$KEY" VPS_HOST="$HOST" VPS_RELEASE="$RELEASE" "$REPO_ROOT/scripts/vps/prune-removed.sh"

# API dependency changes must arrive before the image build, in the same release.
"${RSSH[@]}" "$REPO_ROOT/scripts/vps/api-requirements.lock" "$HOST:$PRODUCT/scripts/vps/api-requirements.lock"
"${RSSH[@]}" "$REPO_ROOT/scripts/vps/deploy-api.sh" "$HOST:$PRODUCT/scripts/vps/deploy-api.sh"

echo "==> rebuilding and restarting api + social"
"${SSH[@]}" "REL='$PRODUCT' bash '$PRODUCT/scripts/vps/redeploy-api.sh'"

echo "==> verifying repo and box agree"
KEY="$KEY" VPS_HOST="$HOST" VPS_RELEASE="$RELEASE" "$REPO_ROOT/scripts/vps/verify-deploy.sh"
