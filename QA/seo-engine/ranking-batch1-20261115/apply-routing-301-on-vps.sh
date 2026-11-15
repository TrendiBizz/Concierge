#!/usr/bin/env bash
# SEO Engine, 15 Nov 2026: OPTIONAL second script, ranking plan item 13 (routing, not HTML).
# 301 the .html twins (/about.html) and trailing-slash URLs (/about/) to the clean URL (/about).
# Run ON the VPS (152.42.239.240) by whoever holds the sanctioned VPS route, only after Omega Boss approves.
# Where: the Node static server website.mjs (container trendi-website-1, mounted at /srv/website.mjs), inside
# asset(), AFTER the _redirects loop (so _redirects and the 410 worker still win) and BEFORE the file lookup.
# Never redirects: /llms.txt, /robots.txt, /sitemap.xml, the IndexNow key, any non-.html file, /concierge/*,
# /cdn-cgi/*, /.well-known/*, /brand|fonts|assets|images/*, /404. Only redirects when site/<page>.html exists.
# Backs up website.mjs, edits it in place (bind mount keeps the same inode), node --check, restarts the
# container, verifies 21 URL expectations + seo-gate.sh (no skip flags). Any failure restores and restarts.
set -euo pipefail
CONTAINER="${TRENDI_WEB_CONTAINER:-trendi-website-1}"
REL="${TRENDI_REL:-/opt/trendi/releases/20261108-vps/website}"
BK="${TRENDI_BK:-/opt/trendi/backups/routing-301-20261115}"
GATE_URL="${GATE_URL:-https://trendibizz.com}"
GATE="$REL/scripts/seo-gate.sh"
MARK='SEO-ENGINE-301'
ANCHOR="  const relative=pathname==='/'?'index.html':pathname.replace(/^\//,'');"
[ -f "$GATE" ] || { echo "gate script missing ($GATE), abort"; exit 2; }
MJS="${WEBSITE_MJS:-$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/website.mjs"}}{{.Source}}{{end}}{{end}}' "$CONTAINER")}"
[ -n "$MJS" ] && [ -f "$MJS" ] || { echo "website.mjs not found (container $CONTAINER), abort"; exit 2; }
echo "website.mjs: $MJS"
grep -q "$MARK" "$MJS" && { echo "already applied ($MARK present), abort"; exit 3; }
n=$(grep -cF -- "$ANCHOR" "$MJS" || true)
[ "$n" = 1 ] || { echo "anchor line found $n times (want 1): website.mjs differs from what this was written for, abort, nothing changed"; exit 3; }
grep -q 'for (const \[from,to,status=' "$MJS" || { echo "_redirects loop not found, abort"; exit 3; }
grep -q 'CSP_NONCE' "$MJS" || echo "WARN: no CSP_NONCE in website.mjs (expected after the 15 Nov nonce deploy); continuing on the anchor check"
[ -e "$BK" ] && { echo "backup dir $BK exists, abort"; exit 2; }
mkdir -p "$BK"; cp -p "$MJS" "$BK/website.mjs.before"; sha256sum "$MJS" > "$BK/SHA256SUMS.before"
printf 'cat %s/website.mjs.before > %s && docker restart %s\n' "$BK" "$MJS" "$CONTAINER" > "$BK/ROLLBACK.txt"
# probes: REDIR must become 301 to the clean URL; SAME must answer exactly as before the change
probe() { curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 20 "$GATE_URL$1"; }
REDIR="/about.html=/about /about/=/about /index.html=/ /pricing.html=/pricing /tools/robots-ai-check.html=/tools/robots-ai-check /tools/robots-ai-check/=/tools/robots-ai-check /news/php2shell-binance-security-2026.html=/news/php2shell-binance-security-2026 /concierge.html=/concierge /ai-receptionist/=/ai-receptionist"
SAME="/ /about /pricing /llms.txt /robots.txt /sitemap.xml /favicon.ico /brand/logo-refresh.svg /concierge/sign-in /concierge/ /tools/ /news/ /404.html /seo-gate-missing.html /ABOUT.html /About /llms.txt/ /robots.txt/ /sitemap.xml/"
KEYJSON="$REL/site/indexnow-key.json"
if [ -f "$KEYJSON" ]; then KEY=$(sed -n 's/.*"key"[^"]*"\([^"]*\)".*/\1/p' "$KEYJSON"); [ -n "$KEY" ] && SAME="$SAME /$KEY.txt /$KEY.txt/"; fi
: > "$BK/probes.before"
for p in $SAME; do printf '%s\t%s\n' "$p" "$(probe "$p")" >> "$BK/probes.before"; done
for pair in $REDIR; do p=${pair%%=*}; printf '%s\t%s\n' "$p" "$(probe "$p")" >> "$BK/probes.before"; done
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/snippet" <<'SNIPPET'
  // SEO-ENGINE-301 (15 Nov 2026, ranking plan item 13): one URL per page.
  // 301 /page.html and /page/ to /page when site/page.html exists. Only lowercase [a-z0-9/-] page paths,
  // so .txt/.xml/.json/.js/.css/images, the IndexNow key, /llms.txt, /robots.txt and /sitemap.xml never match.
  // /concierge/*, /cdn-cgi/*, /.well-known/*, asset folders and /404 are excluded. Query string is kept.
  {
    let clean=null;
    if (/^\/[a-z0-9][a-z0-9\/-]*\.html$/.test(pathname)) clean=pathname.slice(0,-5);
    else if (/^\/[a-z0-9][a-z0-9\/-]*[a-z0-9]\/$/.test(pathname)) clean=pathname.slice(0,-1);
    if (clean==='/index') clean='/';
    const keep=/^\/(concierge|cdn-cgi|\.well-known|brand|fonts|assets|images)\//;
    if (clean && !pathname.includes('//') && !keep.test(pathname) && clean!=='/404') {
      const target=clean==='/'?'index.html':clean.slice(1)+'.html';
      try {
        const real=await fs.realpath(path.resolve(root,target));
        if (real.startsWith(root+'/') && (await fs.stat(real)).isFile())
          return new Response(null,{status:301,headers:{Location:clean+new URL(request.url).search}});
      } catch {}
    }
  }
SNIPPET
awk -v a="$ANCHOR" -v sf="$TMP/snippet" 'index($0,a)==1 && length($0)==length(a){while((getline l < sf)>0) print l} {print}' "$MJS" > "$TMP/new.mjs"
[ "$(grep -c "$MARK" "$TMP/new.mjs")" = 1 ] || { echo "insert failed, abort, nothing changed"; exit 4; }
restore() {
  echo "ROLLING BACK"; cat "$BK/website.mjs.before" > "$MJS"; sha256sum -c "$BK/SHA256SUMS.before"
  docker restart "$CONTAINER" >/dev/null; sleep 3
  bash "$GATE" "$GATE_URL" > "$BK/gate-after-rollback.log" 2>&1 || true
}
cat "$TMP/new.mjs" > "$MJS"; sha256sum "$MJS" > "$BK/SHA256SUMS.after"
docker exec "$CONTAINER" node --check /srv/website.mjs || { echo "node --check failed"; restore; exit 5; }
docker restart "$CONTAINER" >/dev/null
for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$GATE_URL/")" = 200 ] && break; sleep 1; done
: > "$BK/probes.after"; fails=0
for pair in $REDIR; do p=${pair%%=*}; want=${pair#*=}; got=$(probe "$p")
  case "$got" in "301 "*"//"*"$want"|"301 $want") if [ "${got#301 }" = "$want" ] || [ "${got#301 *://*/}" = "${want#/}" ]; then r=OK; else r=FAIL; fi;; *) r=FAIL;; esac
  echo "$r REDIR $p -> $got (want 301 $want)" | tee -a "$BK/probes.after"; [ "$r" = OK ] || fails=$((fails+1)); done
for p in $SAME; do got=$(probe "$p"); was=$(awk -F'\t' -v p="$p" '$1==p{print $2; exit}' "$BK/probes.before")
  if [ "$got" = "$was" ]; then r=OK; else r=FAIL; fails=$((fails+1)); fi
  echo "$r SAME  $p -> $got (before: $was)" | tee -a "$BK/probes.after"; done
if [ "$fails" != 0 ]; then echo "$fails probe(s) failed"; restore; exit 6; fi
if bash "$GATE" "$GATE_URL" 2>&1 | tee "$BK/gate.log"; then echo "GATE PASS"; else echo "GATE FAIL"; restore; exit 1; fi
echo "DONE. Backup and rollback: $BK (ROLLBACK.txt). Repo copy of website.mjs needs the same snippet (branch seo-engine/ranking-batch1-20261115)."
