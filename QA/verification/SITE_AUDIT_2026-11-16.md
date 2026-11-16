# Full site audit and change plan — 2026-11-16

Scope: the live marketing site `https://trendibizz.com` (every URL in the sitemap plus every internal
link found by crawling), the customer surfaces on `concierge.trendibizz.com` (`/owner-ui`, `/studio/`,
`/studio/install`), and the Studio's built assets. Tools used are in the "How this was tested" section.

## Result in one paragraph

The marketing site is structurally healthy: 49 internal URLs crawled, **0 broken internal links, 0 broken
images, 0 horizontal overflow at 390px or 1440px, 0 page errors, 0 unlabeled form fields**, and the repo's
own SEO gate (`site_seo.py check`) passes for 45 pages. The real defects are narrower: a **malformed
Content-Security-Policy on every page**, **9 outbound links that now redirect**, **two competing
customer sign-in portals**, and **both enquiry forms only open a mail draft** (nothing is captured).
The Studio's 16 signed-in tabs were **not** exercised live (needs a session); see "Not verified".

## Findings (FACT = observed in a tool result)

### P1 — fix first

1. **CSP nonce placeholder never substituted (FACT).** `website/_headers` ships
   `script-src 'self' 'nonce-{CSP_NONCE}' …` and Cloudflare's injected inline script carries the literal
   `nonce="{CSP_NONCE}"`. Chrome logs, on **every one of the 45 pages**: *"The source list for
   'script-src' contains an invalid source: 'nonce-{CSP_NONCE}'. It will be ignored"* and *"Executing
   inline script violates … script-src"*. Effect: Cloudflare's injected challenge script is blocked on every
   page (its bot detection is silently off), the console is noisy, and a nonce that is a fixed public string
   protects nothing. Site scripts are all external `'self'`, so visitors see no breakage.
   Fix: remove the nonce source from the header (or have the edge generate real nonces), add a test that
   fails if `{CSP_NONCE}` appears in a served header.
2. **Enquiry mail health check is failing (FACT, from the 21:15 alert earlier in this thread):**
   `cloudflare:routing: 0 enabled rules (expected >=5)` and `inbound:readiness: unparseable response`.
   Customer enquiries may not be reaching the system. Not investigated this session; it outranks cosmetic work.
3. **Both enquiry forms only open an email draft (FACT).** `/contact` and `/concierge-start` build a
   `mailto:` link; the page says "Nothing has been sent." A visitor on a phone with no mail app configured,
   or on a work laptop, loses the lead. Fix: post to a real endpoint (store + notify), keep the mailto as a
   fallback.

### P2

4. **Two customer sign-in portals (FACT).** The site links `Customer sign-in` / `Sign in to your workspace`
   to `concierge.trendibizz.com/owner-ui` (78 references in `website/*.html`), `/concierge/sign-in`
   302-redirects there, while the new app lives at `/studio/`. Decide one front door and redirect the other.
5. **9 outbound links redirect (FACT):** Google crawler docs ×3, RFC 9309, Perplexity bots, OpenAI bots,
   Facebook profile URL (used on 3 pages). Update to the final URLs so the pages do not depend on redirects.
   `cisa.gov` (403) and `binance.com` (202) on `/news/php2shell-binance-security-2026` look like bot
   blocking — check by hand.
6. **12 MB intro video on `/penetration-testing` (FACT: 12,113,360 bytes, `preload="metadata"`).** Headless
   Chromium reported the request aborted; INFERENCE (unverified): no H.264 in headless Chromium, not a real
   fault. Still, offer a smaller/compressed encode for mobile.

### P3

7. `/concierge-start?plan=…` variants share one title (FACT, crawler). They are query variants of one page;
   confirm their canonical points at `/concierge-start`.
8. `chat.trendibizz.com/` returns 404 at the root (FACT). `widget.js` loads fine from it, so this is likely
   intended; add a plain landing or redirect to avoid a dead address.
9. Two things flagged by my scripts were **false positives** and need no change: an "unnamed link" on
   `/llms-txt` (the link has text; it sits in a collapsed section) and 5 "missing" Studio chunks
   (filenames like `container.stylex-Cj771PLO.js` exist in `dist/assets`).

## What passed (FACT)

- 49 URLs: all 200 except `/concierge/sign-in` (intentional 302).
- `http→https`, `www→apex`, `*.html→clean URL`, trailing slash → canonical, all 301; unknown path → 404.
- Titles ≤65 chars, one `<h1>` per page, description ≤160, canonical, JSON-LD, `og:image`, viewport present
  on every page; no `noindex`; no `http://` assets; every image has `alt` and dimensions.
- HSTS, CSP (apart from item 1), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` present.
- `robots.txt`, `sitemap.xml`, `llms.txt` all 200. The repo SEO gate: *OK: 45 pages*.
- Tools, exercised in a browser against trendibizz.com itself: missed-call calculator (10 calls × $2,000 × 50%
  → "10,000 a week · 43,333 a month · 520,000 a year", arithmetic correct); AI-crawler robots checker (returns
  a 9,300-character report naming GPTBot); site snapshot and security check (both return full reports, no
  errors); setup form (bad URL rejected, good URL produces the draft and mailto); contact form (draft + Gmail/
  Outlook fallbacks appear).
- Studio shell: `/studio/`, `/studio/install`, manifest, service worker, icons all 200; 132 built assets
  loaded, none genuinely missing.

## Not verified (UNKNOWN)

- **The 16 signed-in Studio tabs** (Home, Enquiries, Texts, Contacts, Companies, Bookings, Quotes, Products,
  Designs and CAD, Social, Marketing media, Reports, Setup, Channels and permissions, Team, Your CRM, Saved
  replies): they need a session and the local Postgres is down (the known 29 failures). I did not ask for
  credentials. Only their code and bundles were checked.
- Real iPhone/Safari rendering and the home-screen install; only emulated user agents were used.
- Core Web Vitals / Lighthouse scores, and email deliverability of the mailto-based forms.
- Outbound third-party pages' content (status codes only).

## Change plan (in order)

| # | Change | Where | Proof to require |
|---|---|---|---|
| 1 | Investigate and fix the two failing health checks (Cloudflare routing 0 rules; inbound readiness) | box + `scripts/vps/healthcheck.py` | health check green; test inbound through a staged address, never production replay |
| 2 | Remove the `{CSP_NONCE}` placeholder; test that no served header contains `{` | `website/_headers`, `scripts/seo` | headless console free of CSP errors on all 45 pages |
| 3 | Real enquiry capture endpoint for `/contact` and `/concierge-start`, mailto kept as fallback | `api/app`, `website/concierge-start.js`, `main.js` | test + one staged submission; no real SMS/calls |
| 4 | Pick one portal front door; redirect `/owner-ui` ↔ `/studio/` and update the 78 links | `website/*.html`, API | crawl shows one sign-in target |
| 5 | Update the 9 redirecting outbound links; hand-check CISA and Binance | 6 pages | re-run link check: 0 redirects |
| 6 | Compress the intro video; keep poster | `website/media` | file size, plays on iPhone |
| 7 | Studio tab-by-tab live walk-through with a test account | Studio | per-tab screenshot + console clean |
| 8 | Confirm `plan=` canonicals; give `chat.` root a landing | `website`, Caddy | curl |

After each deploy: `scripts/seo/site_seo.py check`, then `scripts/vps/verify-deploy.sh`.

## How this was tested

`/tmp/audit/crawl.py` (httpx; sitemap + link-following crawl, then HEAD/GET every link and asset),
`an.py` (page checks), `br.py` (Playwright Chromium, 390×844 iPhone UA and 1440×900, console / failed
requests / overflow / images / labels), `fn.py` (tool and form behaviour). Scripts are in `/tmp/audit`, not
the repo; results above were produced on 2026-11-16 ~22:40 NZDT.
