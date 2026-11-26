#!/usr/bin/env bash
# Lint website/ with Hallmark sloplint. The linter cannot resolve root-absolute stylesheet hrefs
# ("/styles.css?v=..."), so lint a scratch copy with the stylesheet hrefs made relative. Source untouched.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)/website"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
rsync -a --exclude node_modules "$SRC/" "$TMP/site/"
while IFS= read -r f; do
  rel="${f#"$TMP/site/"}"; depth="$(awk -F/ '{print NF-1}' <<<"$rel")"; up=""
  for ((i=0;i<depth;i++)); do up="../$up"; done
  sed -E -i '' "s#(href=\")/([^\"]*\.css)#\1${up}\2#g" "$f"
done < <(find "$TMP/site" -name '*.html')
node "$HOME/.claude/skills/hallmark/scripts/sloplint.mjs" "$TMP/site/" "$@"
