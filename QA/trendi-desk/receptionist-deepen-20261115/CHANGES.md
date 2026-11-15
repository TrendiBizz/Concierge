# receptionist-deepen-20261115 (Trendi Desk) — STAGED, NOT DEPLOYED

Brief: SEO Engine items 5 + 6 of the 15 Nov ranking plan (Jo: "implement all of these now please", 15:40 NZDT).
Base: live trendibizz.com captured 2026-11-15 15:45 NZDT, x-trendi-release 20261108-vps (VPS/Concierge).
Cloudflare's edge-injected challenge <script> stripped from the snapshot (`live-snapshot/site-clean/`); nothing else changed.
Rebuild: `python3 build.py` (always starts from live-snapshot/site-clean). Local serve: `python3 serve_local.py 8797`.

## Item 5 (H1) — already fixed live, no change made
Live H1 is already "How to choose the best AI receptionist" (fixed in the Mac SEO pass, see TrendiBizz/Concierge
QA/verification/SEO_PASS_2026-11-15.md). Repo origin/main website/best-ai-receptionist.html still has
"…in worldwide" in the H1 + meta: the repo is behind live.

## Item 6 — files to ship (VPS website dir)
- ai-receptionist.html            main words 1,064 -> 2,092
- ai-receptionist-cost.html       main words   675 -> 1,342
- concierge-start.html            main words   760 ->   939
- brand/screenshots/concierge-chat-window.webp   (new, 760x1105, 25 KB)
- brand/screenshots/concierge-setup-request.webp (new, 900x1908, 49 KB)
Untouched: <title>, meta description, og:/twitter:, canonical, every other page, CSS/JS.
JSON-LD: new FAQs mirrored into the existing FAQPage; WebPage.dateModified=2026-11-15 (ai-receptionist, cost). No new types.

## Gate
seo-gate.sh against local serve of the full staged mirror: PASS=20 FAIL=0 WARN=1 (www->apex skipped, local) -> gate-local.txt
Live baseline before: PASS=21 FAIL=0 -> gate-live-baseline.txt

## Update 2026-11-15 ~16:00 NZDT (Omega Boss + SEO Engine rulings; still NOT rebased, NOT deployed)
- concierge-start: removed live leftover "; yearly billing is available after the first three months at USD $2,700" (yearly is sold from day one, Omega Boss/Jo 13:45). Now: "Concierge is USD $250 a month with a 3-month minimum."
- ai-receptionist: added secondary-offer line after "What it does not do" list, linking /seo (SEO and AI visibility).
- ai-receptionist-cost: added secondary-offer line after "When we would tell you not to buy it" list, linking /seo.
- concierge-start: no new link; live body already has "Looking for another service? SEO and AI visibility…" -> /seo.
- Checks: 0 "GST" on staged pages; no "yearly only after month 3" text; every FAQPage Q+A visible word for word (11/9/3 items); head tags unchanged.
- Word counts (main): 2,117 / 1,368 / 926. Local gate PASS=20 FAIL=0 WARN=1.
- Rebase pending: SEO Engine batch 1 + Omega Boss deploys (buy buttons, yearly link, sign-in hrefs, study-noindex/GST) change these pages live.

## Rebase 2026-11-15 16:08 NZDT on live after SEO Engine batch 1 (repo main @ 249ef97) — NOT DEPLOYED
- Fresh full mirror (40 sitemap URLs) in live-snapshot/; previous base kept in live-snapshot-1545/.
- Base bytes for the 3 pages fetched with `Range: bytes=0-` (on-disk, no CF script) into live-snapshot/ondisk/; identical to CF-stripped fetch. Checksums in SHA256SUMS.txt.
- build.py fixes: cost-page FAQ anchor now stops at the FAQ section (new Related block follows it); reviewed-line anchor generalised; tidied "Prices are in USD;  We do not promise leads or sales." -> "Prices are in USD. We do not promise leads or sales." on /ai-receptionist (visible + FAQPage).
- Preserved: titles, metas, og/twitter, SEO Engine Related blocks/links, data-concierge-plan/data-pay-label buttons, yearly link, owner-ui sign-in hrefs (no base href lost; added only /seo and /concierge-start).
- Local gate on full mirror + edits: PASS=20 FAIL=0 WARN=1 (www->apex skipped locally).
