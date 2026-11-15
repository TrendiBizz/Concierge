#!/usr/bin/env bash
# Publish the host tooling (scripts/vps) and prove the box now matches the repo.
#
# Why this exists: on 2026-11-15 the site deploy ran cleanly and then `verify-deploy.sh` failed with
# `scripts/vps: DRIFT` for deploy-site.sh and healthcheck.py. Both are host tooling, published by
# copying — and no script did the copying. The only way to clear the drift was a hand-run rsync, which
# is exactly the kind of undocumented step that produced the three drifts this repository exists to
# prevent. The health check's `deploy:manifest` and `site:seo` checks also run *from this directory on
# the box*, so a stale copy means a stale guard.
#
# Usage:  KEY=./Concierge ./scripts/vps/sync-tooling.sh
# Exit:   0 only when the repo and the box agree afterwards.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
REMOTE="$RELEASE/product/scripts/vps"
KEY="${KEY:-$REPO_ROOT/Concierge}"
SRC="$REPO_ROOT/scripts/vps"

[ -d "$SRC" ] || { echo "no host tooling at $SRC" >&2; exit 1; }

# The box must be traceable to a commit, same rule as the website.
if ! git -C "$REPO_ROOT" diff --quiet -- "$SRC" || ! git -C "$REPO_ROOT" diff --cached --quiet -- "$SRC"; then
  echo "REFUSING: $SRC has uncommitted changes. Commit them first." >&2
  git -C "$REPO_ROOT" status --short -- "$SRC" >&2
  exit 1
fi
UNTRACKED="$(git -C "$REPO_ROOT" ls-files --others --exclude-standard -- "$SRC")"
if [ -n "$UNTRACKED" ]; then
  echo "REFUSING: untracked files in $SRC (git add them first):" >&2
  echo "$UNTRACKED" >&2
  exit 1
fi

COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
echo "syncing $SRC at $COMMIT to $HOST:$REMOTE"
# No --delete: the release tree also holds box-only files (an older compose.yml backup, pycache) that
# are not ours to remove. Junk that macOS leaves behind and Python caches are excluded.
rsync -a --exclude '._*' --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY" \
  "$SRC/" "$HOST:$REMOTE/"

echo "--- verifying parity"
KEY="$KEY" "$REPO_ROOT/scripts/vps/verify-deploy.sh"
