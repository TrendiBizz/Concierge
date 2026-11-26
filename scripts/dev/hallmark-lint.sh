#!/usr/bin/env bash
# Lint website/ with Hallmark sloplint. The linter cannot resolve root-absolute stylesheet hrefs
# ("/styles.css?v=..."), so lint a scratch copy with the stylesheet hrefs made relative. Source untouched.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)/website"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
rsync -a --exclude node_modules "$SRC/" "$TMP/site/"
for f in "$TMP"/site/*.html; do
  sed -E -i '' 's#(rel="stylesheet"[^>]*href=")/#\1#; s#(href=")/([^"]*\.css)#\1\2#' "$f"
done
node "$HOME/.claude/skills/hallmark/scripts/sloplint.mjs" "$TMP/site/" "$@"
