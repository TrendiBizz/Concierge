# Social marks, mobile controls, and a stricter SEO contract (2026-11-16)

## What was asked

- The social connection links were not slick, and the text should be replaced with the actual
  in-colour icons of each network.
- The website's overall UI should be better; check the whole site for improvements.
- SEO should be as high as it can be.

## Social marks

**Studio → Social.** "Connect linkedin organization" and friends were plain text buttons in a row.
They are now a grid of connection cards, each with the network's official full-colour mark, its
name, what it connects, and its state:

- available → **Connect** (or **Add another** when an account is already linked);
- linked → the account name(s) in the card;
- not enabled for this business → a faded card and a `setup` badge.

The composer's account checkboxes carry the same marks. Marks live in
`web/portal/public/social/*.svg` (served from `/studio/social/`), so the Studio does not depend on
the marketing site or an icon CDN.

**Public site footer.** The five text links became circular buttons around the colour marks
(LinkedIn, Facebook, Instagram, YouTube, TikTok), replaced on all 40 pages. Each link keeps a
`<span class="sr-only">` name, so it still has an accessible name and a crawlable label — an
icon-only link with no text is a link nobody can describe. `youtube.svg` was added to
`website/brand/social-logos/`; the other four marks already existed and were already used on
`/concierge`.

## UI defects found and fixed on the way

1. **The closing call-to-action was white on white.** `.btn:not(.ghost){color:#fff}` was declared
   after `.cta-band .btn{color:#6540aa}` at the same specificity, so it won: measured live,
   `color rgb(255,255,255)` on `background rgb(255,255,255)` — the "Get started with Concierge"
   label was invisible inside its own white pill on every page with a closing band. The repair is
   declared last on purpose, and a test pins that order. Live now: `rgb(91,47,168)` on white.
2. **The eyebrow above the purple band was purple on purple** (`#8057b1` on `#7142d6`, ~1.5:1).
   Now `#efe6ff`.
3. **The chat launcher was a half-screen bar on a phone** — a 300×53 fixed button with the full
   call-to-action, sitting over the content it was selling. At ≤600px it is now a 56×56 mark. The
   button keeps its `aria-label`, so the label is not lost to assistive tech.
4. **The language pill covered the price line on a phone.** At ≤600px it collapses to a 44×44
   globe; the panel still opens from it.

Measured live at a 390px viewport after the change: launcher 56×56, language control 44×44,
`scrollWidth === clientWidth === 390` (no horizontal overflow).

### A false alarm, recorded so it is not re-raised

A headless-Chrome screenshot at `--window-size=390` looked clipped: text cut mid-word, the menu
button missing. That was the tool, not the site — headless Chrome clamps the window to a 500px
minimum and then crops the image. Re-measured with `Emulation.setDeviceMetricsOverride(390, 844,
mobile)` over the DevTools protocol: viewport 390, `scrollWidth` 390, Menu button visible at
`right: 372`. **Do not "fix" mobile overflow from a `--window-size` screenshot.**

## SEO: a stricter contract, not a promise

The deploy gate already covered canonical, robots, h1, snippet length, dates, internal links,
sitemap parity, IndexNow key and `robots.txt` policy. Six more rules now fail the deploy:

- structured data that does not parse (a broken `@graph` silently removes every rich result);
- a page with no JSON-LD at all;
- an `<img>` with no `alt` attribute (`alt=""` is allowed — that is a decorative decision);
- a heading level that is skipped (h1 → h3);
- a meta description duplicated on another page;
- an `og:image` that is not an absolute https URL.

Running it found four real heading jumps — `/`, `/concierge`, `/seo`, `/penetration-testing` — each
an `h3` list that followed the `h1` with no `h2` between. Each got a visually hidden `h2` naming
the block, so the outline is correct without changing the design. Those four pages' `dateModified`
and visible date moved to 2026-11-16, and the sitemap was regenerated rather than hand-edited.

What this does **not** do is promise rankings. The remaining levers are content and off-site work
already listed in HANDOFF §3 items 7 and 21–27 (Search Console/Bing, city pages, shareable reports,
link earning). The technical contract is now the strongest it has been; it cannot manufacture a
result for a query nobody has written a page for.

## Proof

- `api/tests/test_site_seo.py` — 52 tests; six new ones for the new rules; the clean-fixture helper
  now emits a unique description and an absolute `og:image`.
  Mutation: the heading-order block removed → `test_a_heading_that_skips_a_level_is_reported` fails.
- `api/tests/test_social_icons.py` — 10 tests: the icon footer on all 40 pages, the accessible
  names, every declared mark present, the Studio building from `SOCIAL_NETWORKS`, the phone rules
  for the launcher and the language pill, the cache-version bumps, and the CTA repair ordering.
- Full suite: **1430 passed, 19 skipped, 29 failed** — the same 29 local-Postgres connection
  failures (HANDOFF item 34). `tsc -b` clean, portal build clean.
- Deployed: site (`verify-deploy` → **OK: repo and box agree**, gate OK on 45 pages, IndexNow HTTP
  200 for 38 URLs), Studio (build served, `/studio/social/*.svg` all 200), API (widget.js with the
  phone launcher rule).
- Live screenshots: `social-icons-footer-2026-11-16.png`,
  `mobile-floating-controls-2026-11-16.png`. Computed colours read back from the live page:
  CTA `rgb(91,47,168)` on `rgb(255,255,255)`, eyebrow `rgb(239,230,255)`.

## Open

- The Studio's Social page was verified by types, build and source tests; it sits behind sign-in,
  so the connection cards have not been looked at on a signed-in screen.
- The phone checks are device emulation at 390px, not a physical handset.
