#!/usr/bin/env bash
# Omega Boss, 15 Nov 2026: deploy Trendi Desk receptionist-deepen-20261115 (3 HTML + 2 new webp). SEO Engine passed the lock.
set -euo pipefail
SITE=/opt/trendi/releases/20261108-vps/website/site
GATE=/opt/trendi/releases/20261108-vps/website/scripts/seo-gate.sh
BK=/opt/trendi/backups/receptionist-deepen-20261115
URL=https://trendibizz.com
BASE='63cd29bbf1f8505cae17d90b0327545cd75fba47f12c0eb7d895ceee66734034  ai-receptionist-cost.html
6ea723c5259f37a2d6b69779b3d69f4e91b1004dd395e75471c006042e5b41b2  ai-receptionist.html
9704e0de8eea8bb16936ab8af72afb651d5324086e10d685519c320d10909d10  concierge-start.html'
NEW='0109ce02d66c7f00ada164dbbadd85113cc72c15c4116fee0d62e46fddbf7c8b  ai-receptionist.html
983294140c2b655e9eab96d66dd3b60aa71b9ba3b683b38ff4bd9504511acb9f  ai-receptionist-cost.html
3341241493eb58d829676229be9520e1aa69820fab6b4320bc859fad634eea69  concierge-start.html
fe64a4d596ba06a0c8acbf67361861cdbcb140f7ba8952eeb3afc59f3af64857  brand/screenshots/concierge-chat-window.webp
5e95080ee90a156125c4cc2500c95fb79d91fec6702df6ce621b471be3c61976  brand/screenshots/concierge-setup-request.webp'
[ -f "$GATE" ] || { echo "no gate, abort"; exit 2; }
cd "$SITE"
printf '%s\n' "$BASE" | sha256sum -c --quiet || { echo "ABORT: live base drifted, nothing changed"; exit 3; }
for f in brand/screenshots/concierge-chat-window.webp brand/screenshots/concierge-setup-request.webp; do [ -e "$f" ] && { echo "ABORT: $f already exists"; exit 3; }; done
[ -d brand ] || { echo "ABORT: no brand dir"; exit 3; }
[ -e "$BK" ] && { echo "ABORT: $BK exists"; exit 2; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
base64 -d > "$TMP/p.tgz" <<'PAYLOAD'
