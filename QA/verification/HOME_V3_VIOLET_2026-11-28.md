# Site v3: "violet turned up", Gambetta + Switzer, light and dark, all pages (2026-11-28)

Status: **branch `claude/home-violet-gambetta`, draft PR, NOT deployed.** Merge and deploy are Omega Boss's call (docs/AGENT_WORKING_ORDER.md).

## Why
Design review of trendibizz.com (owner request, 2026-11-28). Findings on the live site:
- Display serif was a system stack (Iowan Old Style, Palatino, Georgia), so headlines differed per device.
- Body font Plus Jakarta Sans is a very common default.
- Peach and green panels (`--warn-wash`, `--ok-wash`) and a purple gradient on the demo panel and page headers, which the owner disliked.
- The owner chose the "violet turned up" palette (lilac ground, deep ink, Trendi violet, one hot-pink highlight) with a light and a dark version and Fontshare type, and asked for it on every page (first version covered the homepage only).

## What changed
- `website/site-v3.css` (new, loaded last by all 57 pages): re-declares the shared tokens and their aliases (aliases are resolved at `:root` in styles.css, so they must be re-declared), light and `prefers-color-scheme: dark`. Because the components are token-driven, they pick the palette up without per-component edits. Also: display/text fonts, flat ruled page headers instead of gradients, ruled rows instead of boxed cards (offers, steps, tools, FAQ), flat dark closing band and featured price card. Homepage-only touches (hero size, pink highlight on "busyness.", tag-style tick list, flat walkthrough) are scoped to `body.page-index` or to classes only used there.
- Decorative peach and green washes are recoloured as violet tints at token level. **Status colours are untouched**: `--ok`, `--warn`, `--danger` still drive pass / review / error badges, toasts and the tool results.
- `website/fonts/`: Gambetta 500/600/700 and Switzer 400/500/600 (woff2, self-hosted) and `FONTSHARE-NOTES.txt`.
- All 57 `website/**/*.html`: one `<link>` to `/site-v3.css?v=20261128` after trendi-ui.css, and the Plus Jakarta preload swapped for Gambetta 600 and Switzer 400 preloads. No copy, structure, i18n key, schema or script changed.

Not changed: `styles.css`, `refresh.css`, `layout.css`, `ui/trendi-ui.css`, `_headers` (CSP `style-src 'self'` and `'self'` font loading already allow this), logos, `BRAND.md`, the product apps under `web/`, `sites/`, `crm/` etc.

## Proof (local, 2026-11-28)
- `python3 scripts/seo/site_seo.py check`: OK, 57 pages. `scripts/seo-gate.sh`: GATE RESULT: PASS (22 pass, 0 fail, 0 warn).
- API site tests: `test_site_trendi_ui`, `test_site_seo`, `test_site_pricing_consistency`, `test_site_redirects`, `test_page_api_contract`, `test_website_case_redirect`: 88 passed. (One test failed on a depth-1 clone because it walks git history; it passes once the clone has history.)
- Served `website/` locally and loaded **every page** (57) at 1440 and 390 px, light and dark (228 page-views): no horizontal overflow, no failed asset requests, body font Switzer and headings Gambetta on all.
- Eyeballed screenshots in light and dark of: home, concierge, pricing, SEO, penetration testing, about, contact, terms, site snapshot tool, security check, a news article, a comparison page, 404.
- Contrast computed from tokens: light, ink 15.5, muted 6.5, link 7.4, button text 8.6, highlight text 6.3; dark, ink 16.7, muted 8.3, link 8.3, button text 8.3, highlight text 6.6, band text 8.6 and 6.3. All above 4.5.

## Not verified
- Safari, Firefox, real phones; the language switcher with translated copy (strings unchanged, but longer translations may wrap differently).
- Every state of the interactive tools (results panels with pass/review/error colours were not exercised), forms after submission, and the hero walkthrough beyond its first step.
- The product apps (portal, CRM, etc.) have their own CSS and were not touched.
- Fontshare licence text: the notes file says to read and keep a copy before launch.
- `BRAND.md` still lists the older palette and the system font stack; it needs updating if this is approved.

## Known limits
- The owner's "front desk log" hero and "a day at the desk" timeline are NOT implemented: they need new illustrative copy and translations, which is a Trendi Desk and honesty-check decision.
- Status badges keep their green / amber / red meaning, so green and amber still appear on tool results by design.

## Rollback
Remove the `site-v3.css` `<link>` lines and restore the Plus Jakarta preload (a single scripted revert of the head lines), or revert the commit. Nothing else depends on the new files.
