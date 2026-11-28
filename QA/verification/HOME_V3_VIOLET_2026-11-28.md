# Homepage v3: "violet turned up", Gambetta + Switzer, light and dark (2026-11-28)

Status: **branch `claude/home-violet-gambetta`, draft PR, NOT deployed.** Merge and deploy are Omega Boss's call (docs/AGENT_WORKING_ORDER.md).

## Why
Design review of trendibizz.com (owner request, 2026-11-28). Findings on the live homepage:
- Display serif was a system stack (Iowan Old Style, Palatino, Georgia), so headlines differed per device.
- Body font Plus Jakarta Sans is a very common default.
- Peach and green panels (`--warn-wash`, `--ok-wash`) and a purple gradient demo panel, which the owner disliked.
- The owner chose the "violet turned up" palette (lilac ground, deep ink, Trendi violet, one hot-pink highlight) with a light and a dark version, and Fontshare type.

## What changed (homepage only)
- `website/home-v3.css` (new): every rule scoped to `body.page-index`. Re-declares the shared tokens and their aliases (aliases are resolved at `:root` in styles.css, so they must be re-declared), light and `prefers-color-scheme: dark`.
- `website/fonts/`: Gambetta 500/600/700 and Switzer 400/500/600 (woff2, self-hosted), plus `FONTSHARE-NOTES.txt`.
- `website/index.html`: swapped the Plus Jakarta preload for Gambetta 600 and Switzer 400 preloads; added one `<link>` to `/home-v3.css?v=20261128`. No copy, structure, i18n key, schema or script changed.
- Visual changes: hot-pink marker highlight on "busyness."; luggage-tag style for the tick list; flat (no gradient) walkthrough and closing band; rules instead of boxed cards for services, steps, tools and FAQ; peach and green panel tints removed; dark mode token set.

Not changed: every other page, `styles.css`, `refresh.css`, `layout.css`, `_headers` (CSP `style-src 'self'` and font loading from `'self'` already allow this), logos, `BRAND.md`.

## Proof (local, 2026-11-28)
- `python3 scripts/seo/site_seo.py check`: OK, 57 pages.
- `scripts/seo-gate.sh`: GATE RESULT: PASS (22 pass, 0 fail, 0 warn).
- Served `website/` locally and screenshotted with Chromium at 1440 and 390 px, light and dark: Gambetta 600/700 and Switzer 400/500/600 load; no horizontal overflow in any of the four.
- Contrast (WCAG ratio, computed from the token values): light, ink 15.5, muted 6.5, link 7.4, button text 8.6, highlight text 6.3; dark, ink 16.7, muted 8.3, link 8.3, button text 8.3, highlight text 6.6, band text 8.6 and 6.3. All above 4.5.

## Not verified
- Real devices, Safari and Firefox, and the language switcher with translated copy (strings unchanged, but longer translations may wrap differently).
- The hero walkthrough's interactive states beyond the first step.
- Fontshare licence text: the notes file says to read and keep a copy before launch.
- Brand guide: `BRAND.md` still lists the older purple palette and the system font stack. The homepage now differs from it until the owner approves this and the guide is updated.

## Known limits
- Only the homepage is restyled, so it will look different from the other pages until they are done.
- The owner's "front desk log" hero and "a day at the desk" timeline are NOT implemented: they need new illustrative copy and translations, which is a Trendi Desk and honesty-check decision.

## Rollback
Remove the `home-v3.css` `<link>` from `website/index.html` and restore the Plus Jakarta preload. Nothing else depends on the new files.
