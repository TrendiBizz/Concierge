# 2026-11-27 Option A restyle, dark mode, lint clean, stale chat price

## Cause
- Site CSS was a layered pile of literal colours (white, navy, purple), so Hallmark sloplint gave 639 FAIL across 59 files; dark mode was half-working (refresh.css pinned `color-scheme:light` and redefined tokens).
- Homepage and /concierge showed a chat screenshot answering "USD $250 a month, $750". The live chat agent prompt (`concierge-stack/agent/agent.py`) still said USD 250 and quoted a yearly figure; the pricing test did not cover that file.

## Fix
- One token block in `website/styles.css` (light = Option A warm paper, aubergine ink, purple on actions; dark under `prefers-color-scheme: dark`). All colour literals in the 5 CSS files became tokens; square 4px radius, no shadows; serif headings; global focus-visible, :active, :disabled, `overflow-x: clip`; white header/footer logo in dark via `content:url(logo-horizontal-dark.svg)`.
- Copy (49 pages): removed eyebrow labels, middle dots, dashes, glued arrows; long headings where a short one read as an eyebrow; `<em>` in h1 became a span; emoji play glyph became SVG; walkthrough prev/next arrows kept as SVG. No ids, hrefs, forms or scripts changed.
- Price: agent.py now says USD 199, 3-month minimum, then month to month, no yearly figure. Stale screenshot figure removed from index.html and concierge.html until a real recapture after deploy (do not fake one).
- `scripts/dev/hallmark-lint.sh` lints a scratch copy (sloplint cannot resolve root-absolute stylesheet hrefs).

## Proof
- sloplint: 639 FAIL -> 0 FAIL (REFLEX/WARN remain, advisory).
- `api/tests/test_site_pricing_consistency.py` now covers agent.py and 750; mutation check: agent.py set to USD 250 -> test failed; restored.
- `test_social_icons.py` pins updated to token CSS. Full suite 1928 passed, 42 skipped. `site_seo.py check` OK, `seo-gate.sh` GATE RESULT: PASS.
- Headless Chrome light and dark screenshots of index, concierge, pricing checked.

## Open
- Deploy not authorised. After deploy, recapture the chat screenshot from the live widget and restore the figure; bump `?v=` on CSS refs and purge Cloudflare.
- Not yet screenshot-checked in dark: the other ~50 pages.
