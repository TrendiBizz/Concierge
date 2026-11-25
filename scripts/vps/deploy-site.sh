#!/usr/bin/env bash
# The only supported way to publish the website.
#
# Why this exists: on 2026-11-15 the site lived in a loose directory
# (/Users/jo/work-staging/trendibizz-live/site) that was not a git repository, three agents edited it,
# and 17 files including 3 pages reached production that had never been committed. This script
# refuses to publish anything that is not committed, and stamps a manifest on the box so that a
# hand edit there is detected by the health check.
#
# Usage:  KEY=./Concierge ./scripts/vps/deploy-site.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VPS_HOST:-root@152.42.239.240}"
RELEASE="${VPS_RELEASE:-/opt/trendi/releases/20261108-vps}"
REMOTE="$RELEASE/website/site"
KEY="${KEY:-$REPO_ROOT/Concierge}"
SRC="${SITE_SRC:-$REPO_ROOT/website}"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")

[ -d "$SRC" ] || { echo "no website source at $SRC" >&2; exit 1; }

# 1. Nothing uncommitted may be published. This is the whole point of the script.
if ! git -C "$REPO_ROOT" diff --quiet -- "$SRC" || ! git -C "$REPO_ROOT" diff --cached --quiet -- "$SRC"; then
  echo "REFUSING: $SRC has uncommitted changes. Commit them first — production must be reproducible." >&2
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
echo "deploying $SRC at $COMMIT to $HOST:$REMOTE"

# 1b. The site's technical SEO contract must hold before anything is published. A missing canonical,
#     an accidental noindex, a sitemap that disagrees with the pages or a weakened robots.txt costs
#     rankings for months, and none of it is visible in a browser. Fail here, not in Search Console.
python3 "$REPO_ROOT/scripts/seo/site_seo.py" check
python3 "$REPO_ROOT/scripts/seo/link_audit.py"  # dead links, missing anchors, button loops; nonzero blocks deploy

# 1c. Remember what was live, so IndexNow can be told exactly which pages changed. A failure to read
#     it is not fatal: the deploy is still correct, it just cannot report the diff.
PREVIOUS=""
PREVIOUS="$("${SSH[@]}" "$HOST" "python3 -c \"import json;print(json.load(open('$REMOTE/.deploy-manifest.json')).get('commit',''))\"" 2>/dev/null || true)"
if [ -n "$PREVIOUS" ] && git -C "$REPO_ROOT" cat-file -e "$PREVIOUS^{commit}" 2>/dev/null; then
  echo "previous deploy on the box: ${PREVIOUS:0:8}"
else
  PREVIOUS=""
fi

# 2. Ship the files. --delete keeps production identical to the repo; AppleDouble files from macOS
#    are excluded because they are not part of the site and would be served as junk.
rsync -a --delete --exclude '._*' --exclude '.deploy-manifest.json' \
  -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -i $KEY" \
  "$SRC/" "$HOST:$REMOTE/"

# 3. Stamp the manifest: commit, time, and a hash per file. The health check compares the deployed
#    tree against this, so an edit made directly on the box is reported instead of silently living on.
"${SSH[@]}" "$HOST" "cd '$REMOTE' && python3 - '$COMMIT' <<'PY'
import hashlib, json, os, sys, datetime
root = '.'
files = {}
for base, _dirs, names in os.walk(root):
    for name in names:
        if name.startswith('._') or name == '.deploy-manifest.json':
            continue
        path = os.path.join(base, name)
        rel = os.path.relpath(path, root)
        with open(path, 'rb') as handle:
            files[rel] = hashlib.sha256(handle.read()).hexdigest()
manifest = {'commit': sys.argv[1], 'deployed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': files}
with open('.deploy-manifest.json', 'w') as handle:
    json.dump(manifest, handle, indent=1, sort_keys=True)
print('manifest written:', len(files), 'files')
PY"

echo "--- verifying parity"
KEY="$KEY" SITE_MIRROR="$SRC" "$REPO_ROOT/scripts/vps/verify-deploy.sh"

# 3b. website.mjs reads _headers and the worker once at start (it re-reads _redirects itself), so a
#     file sync alone leaves a long-running process on the old tables. Restart only the website
#     service: no postgres, api or volumes. Verify ran first because it checks the files on disk.
echo "--- restarting the website service"
"${SSH[@]}" "$HOST" "cd '$RELEASE/product/scripts/vps' && podman compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile public restart website >/dev/null"
sleep 5
if ! curl -fsS -o /dev/null --max-time 15 "${SITE_URL:-https://trendibizz.com}/"; then
  echo "WARNING: the site did not answer after the website restart; check the box before leaving" >&2
  exit 1
fi

# 3c. HTML is cached at the Cloudflare edge (Cache-Control s-maxage in website/_headers plus the zone cache
#     rule), so a deploy that does not purge would serve the old pages for up to an hour. Purge everything for
#     the zone: the site is small and every deploy can change any page. The token comes from the environment
#     (CF_API_TOKEN) or the macOS Keychain item named by CF_KEYCHAIN_ITEM (default trendi-cf-deploy-cache-token:
#     it holds Cache Purge + Cache Settings Write + Zone Read on zone trendibizz.com only, nothing else; trendi-cloudflare-token cannot purge); it is never printed. Set
#     SKIP_CF_PURGE=1 only when you know the edge holds nothing stale.
if [ "${SKIP_CF_PURGE:-0}" = "1" ]; then
  echo "WARNING: SKIP_CF_PURGE=1, Cloudflare cache NOT purged" >&2
else
  CF_TOKEN="${CF_API_TOKEN:-$(security find-generic-password -s "${CF_KEYCHAIN_ITEM:-trendi-cf-deploy-cache-token}" -w 2>/dev/null || true)}"
  if [ -z "$CF_TOKEN" ]; then
    echo "FAILED: no Cloudflare token (set CF_API_TOKEN or the Keychain item ${CF_KEYCHAIN_ITEM:-trendi-cf-deploy-cache-token}); the edge may serve stale HTML" >&2
    exit 1
  fi
  CF_ZONE="${CF_ZONE_ID:-$(curl -fsS --max-time 20 -H "Authorization: Bearer $CF_TOKEN" "https://api.cloudflare.com/client/v4/zones?name=trendibizz.com" | python3 -c 'import sys,json;r=json.load(sys.stdin)["result"];print(r[0]["id"] if r else "")' 2>/dev/null || true)}"
  if [ -z "$CF_ZONE" ]; then echo "FAILED: could not find the trendibizz.com zone for the cache purge" >&2; exit 1; fi
  if curl -fsS --max-time 30 -X POST -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" \
       --data '{"purge_everything":true}' "https://api.cloudflare.com/client/v4/zones/$CF_ZONE/purge_cache" | python3 -c 'import sys,json;sys.exit(0 if json.load(sys.stdin).get("success") else 1)'; then
    echo "Cloudflare cache purged"
  else
    echo "FAILED: Cloudflare cache purge was refused; the edge may serve stale HTML" >&2; exit 1
  fi
fi

# 4. Tell IndexNow (Bing, Yandex, Seznam and Bing's partners — which feed ChatGPT search) which pages
#    changed since the previous deploy. Google does not use IndexNow, so this is not a ranking step;
#    it is the difference between a change being noticed in hours rather than weeks.
#    Never fatal: a ping failure says nothing about whether the site is correct.
if [ -n "$PREVIOUS" ]; then
  python3 "$REPO_ROOT/scripts/seo/site_seo.py" ping --changed-in "$PREVIOUS" || \
    echo "IndexNow ping failed; the deploy itself is complete" >&2
else
  echo "IndexNow: no previous manifest commit to diff against; no ping sent"
fi
