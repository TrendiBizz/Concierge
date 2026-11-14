# trendibizz.com link/menu audit — what was fixed, proved, and what needs Stripe or Cloudflare

Source audit: 14 Nov 2026, 41 pages + the owner app, 3,448 element checks. Written to the repo
because the site's deploy source is **not** the trendi-site checkout on this machine — see §5.

## 1. Fixed and verified live

| # | Audit finding | Cause | Fix | Proof (live) |
|---|---|---|---|---|
| 1 | Five "pricing" links went to `/#pricing`, which does not exist | guides were written before `/pricing` existed | all five now `/pricing` | `grep -c '#pricing'` on /ai-visibility = 0 |
| 2 | /terms used the banned word "free" | stale copy | "The public tools on this site…" | /terms live text |
| 3 | support@ label opened `mailto:admin@` | a `data-email` attribute that `site-i18n.js` rewrites | attribute removed; label and address agree | live anchor: `mailto:support@trendibizz.com` with that label |
| 4 | Footers linked `/nz-ai-seo`, a 301 | page renamed to /ai-seo-services | footer points at the final URL (4 pages) | `grep -c nz-ai-seo` on /about = 0 |
| 5 | Five sitemap pages had no inbound links | they were only ever in sitemap.xml and llms.txt | a "By industry" block on /ai-receptionist links all five | each now has ≥1 inbound link |
| 6 | 🌐 Language button untappable on phones (35 pages) | the chat launcher is a fixed 300×53 button at left 70px / bottom 20px with z-index 2147483000 and later in the DOM — it sat exactly on the pill | on ≤600px the pill moves to `bottom: 88px` and sits above the launcher in the stack | 390px: `elementFromPoint` at the pill's centre returns the pill, and a real tap opens the panel (4 pages) |
| 7 | /privacy and /terms had no main menu | both use an older two-element header | replaced with the site header (8 links + ☰ Menu) | 390px: menu button opens `#main-nav` with 8 links; 1280px: 8 visible links |
| 8 | Two OWASP links 308-redirected | OWASP moved its project URLs | pointed at `/projects/web-security-testing-guide` and `/projects/top-ten` | live hrefs |
| 9 | `concierge.trendibizz.com/` answered 404 | the gateway's path allowlist had no `/` entry | `/` added to the allowlist; the API answers `GET /` with a 307 to `/owner-ui` | `root:307 -> https://concierge.trendibizz.com/owner-ui` |
| 10 | Owner app had no favicon (`/favicon.ico` 404) | nothing served it | routes for `/favicon.ico` and `/favicon.svg` serving the Studio icon | `plain favicon.ico now: 200`, `image/svg+xml` |
| 11 | Business number field used `+64278817368` — a real NZ mobile — as its placeholder | copied from the contact number | same obvious dummy as the other field, `+64211234567` | live owner-ui HTML |

Also fixed while doing it — **a deploy trap that made edits invisible**: `site-i18n.css` had no
`_headers` cache rule, so Cloudflare served a cached copy (`cf-cache-status: HIT`, age 6,706s) and
an edited stylesheet never reached visitors. The file now carries `max-age=300, must-revalidate`,
and the references are versioned (`?v=20261114b`).

## 2. Mutation proofs
- **Language pill**: reverting the mobile rule and re-deploying → `tappable: False` at 390px;
  restoring it → `True` and a real tap opens the panel.
- **Owner host**: `GET /` reverted to 404 → the guard fails; `/favicon*` routes renamed → the guard
  fails; the real number put back as a placeholder → the guard fails. All restored, 3/3 green.
- The remaining fixes are copy and link changes, proved by the live greps in §1.

## 3. Tests
`api/tests/test_site_audit_fixes.py` — three guards (root redirect, favicon content type and size,
and a scan that no real-looking phone number is used as a placeholder in `owner.html`).
Whole suite: **1211 passed**.

## 4. Deliberately not changed here
- **Instagram footer link** sends logged-out visitors to a login wall. That is Instagram's
  behaviour, not a broken link; the profile is real.
- **`/glossary`** is `noindex` and not in the sitemap by design; the study page is unlinked on
  purpose. Neither is a defect.
- **`/tools/site-check`** carries no language widget (the tool pages never included the i18n
  script). Left as it was; noted here so it is not mistaken for a regression.

## 5. The site's source of truth — a real finding
The live site is served by the `trendi-website-1` container from
`/opt/trendi/releases/20261108-vps/website/site` via `scripts/vps/website.mjs`, running the
`deploy_known_good/_worker.js` bundle. **None of the checkouts on this machine matched it**: the
`trendi-site` clones (`work-staging/trendi-site`, `trendi-site-web`, `OpenBot/Shared/trendi-site`)
are behind production and are missing `tools/`, `research/`, `news/`, `refresh.css` and
`site-i18n.*` entirely, while `concierge-integration/website/` is a subset that lacks the same
pages. Deploying either with `--delete` would have deleted live pages.

So the work was done on a mirror pulled from production
(`/Users/jo/work-staging/trendibizz-live/site`), edited, and pushed back with `rsync -c` (no
`--delete`). That works, but the site is not reproducible from its repo, which is an operational
risk worth fixing next: reconcile `trendi-site` with production and add a `deploy-site.sh` in the
same shape as `deploy-studio.sh` (stage → permissions → verify), so a future edit cannot delete a
page or serve a stale stylesheet.

## 6. Needs an operator — Stripe and Cloudflare (money and edge settings)
1. **Stripe checkout currency text (High).** "Trendi — Monthly" and "Trendi — Deposit" carry the
   product text "Prices in NZD excluding GST", but the site and the charge are USD (US$1,500/month;
   US$1,000 + US$150 GST deposit). Change that product text to read USD, or change the charge —
   only Jo can, in the Stripe dashboard. Until then a buyer sees two currencies for one price.
2. **Concierge payment link merchant name (Medium).** The checkout header shows `9429051967215`
   (the NZBN) instead of Trendibizz.com, and the link sits on a different Stripe account suffix
   (`…04800`) from the SEO links (`…cEw0x`). Set the public business name on that account and
   confirm the account is intended.
3. **CSP blocks Cloudflare's injected script (Low).** Cloudflare injects an inline
   `__CF$cv$params` script; `script-src` has neither a hash nor a nonce for it, so it is blocked and
   logs 59 console errors. Fixing it means turning off Cloudflare's JavaScript detections for this
   zone (or adding a nonce at the edge) — a Cloudflare dashboard change, not a site change.
4. **YouTube channel bio** says "Run a free site check at trendibizz.com" — off-site, breaks the
   same no-"free" rule; needs a YouTube profile edit.
