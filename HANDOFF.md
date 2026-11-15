# HANDOFF — Trendi Concierge

**Read first:** `AGENTS.md` in this repo (the working agreement — enforced by tooling, and it now
includes the website's technical SEO contract), then the QA record matching the area you touch.
Records from 2026-11-15: `SYSTEM_AUDIT_2026-11-15.md` (audit), `SEO_PASS_2026-11-15.md` (content),
`SEO_GROWTH_2026-11-15.md` (growth implementation — the most recent), `EMAIL_ENGAGEMENT_2026-11-15.md`,
`CENTRAL_REPO_2026-11-15.md`.

## 1. Project and repo

- **Repo:** `/Users/jo/work-staging/concierge-integration`, branch `main` (deployed).
  HEAD `2b83e8c`. Working tree clean at handoff time.
- **Live:** `https://trendibizz.com` (site, 45 indexable URLs), `https://concierge.trendibizz.com/studio/`
  (portal), `https://chat.trendibizz.com/demo/pukeko-construction` (widget).
- **VPS:** `root@152.42.239.240`, key = repo file `./Concierge`
  (`ssh -o BatchMode=yes -o IdentitiesOnly=yes -i ./Concierge root@…`).
  Release dir `/opt/trendi/releases/20261108-vps`.
- **Deploy — do not improvise.**
  - Site: `KEY=./Concierge ./scripts/vps/deploy-site.sh`. Refuses a dirty tree, runs
    `python3 scripts/seo/site_seo.py check`, stamps `.deploy-manifest.json`, verifies, then pings
    IndexNow for the pages that changed.
  - Host tooling (`scripts/vps/`, including the health check): `KEY=./Concierge ./scripts/vps/sync-tooling.sh`.
    **New this session** — without it, editing the health check left `verify-deploy` red forever.
  - API: `rsync api/app/` into `product/api/app/` then `bash scripts/vps/redeploy-api.sh`.
  - Portal: `KEY=./Concierge ./scripts/vps/deploy-studio.sh`.
- **Verify before claiming anything is deployed:** `KEY=./Concierge ./scripts/vps/verify-deploy.sh`
  → must print `OK: repo and box agree` (currently api/app 107 · scripts/vps 38 · website/site 61).
- **Tests:** `cd api && TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres python3 -m pytest -q`
  → **1419 passed**.
- **Health (on the box):** `python3 scripts/vps/healthcheck.py --no-alert` →
  **46 ok / 1 warn (`sms:inbound`) / 0 fail**.
- **Website technical SEO:** `python3 scripts/seo/site_seo.py check` (the deploy gate),
  `python3 scripts/seo/site_seo.py sitemap --write` (the sitemap is generated, never hand-edited).
- **Earlier record:** `HANDOFF_ARCHIVE_2026-11-15_1430.md` holds the session-by-session detail
  (§6a–§6q, §7, §8). Nothing there was dropped; the worklist below is the current list.

## 2. What the 2026-11-15 sessions did

The first three streams are recorded in their own files. The last one is this session:

1. **Audit** — 12 defects found and fixed (invitation sign-in crash, service-worker recovery, settings
   nav, missing h1s, mobile overflow, baked-in SSH key, silent backup failure, missing restore drill,
   unmonitored SIP firewall, `api.env` sourcing bug, stale cron copy). See `SYSTEM_AUDIT_2026-11-15.md`.
2. **SEO content pass** — nine thin money pages grown to 903–1,238 words, ten snippets trimmed,
   `/ai-visibility` turned into a guides index, a bulk "worldwide" geo rewrite reverted in seven
   places, and a `site:pages` health guard. See `SEO_PASS_2026-11-15.md`.
3. **Email engagement + mail auth** — first-party click tracking, Brevo events on the timeline,
   HTML alternative, pending-invites list, `email:auth` check. DKIM was never missing (Brevo
   publishes at `brevo1`/`brevo2`) — that false alarm is recorded so it is not re-raised.
4. **One central repository, enforced** — the site publishes only from this repo, with a deploy
   manifest and a checksum parity check. See `CENTRAL_REPO_2026-11-15.md`.
5. **SEO growth implementation (this session)** — the outside audit's seven ideas, implemented as far
   as they can be without inventing facts. Full detail in `SEO_GROWTH_2026-11-15.md`; the short version:
   - A **technical SEO contract** now gates every deploy and is checked live (`site:seo`): canonical,
     `noindex`, `dateModified`, snippet length, internal links, sitemap parity, `robots.txt` policy,
     IndexNow key. `site:data` guards the research data's freshness.
   - **Seven live defects fixed**, found by the guard on its first run: 21 AppleDouble files committed
     to the web root; `/glossary` (1,043 words) `noindex` and missing from the sitemap; 11 pages with
     no `dateModified`; 13 wrong sitemap `lastmod` values, one malformed `<url>`, one missing `lastmod`;
     the research page linked from nowhere; a Dataset with no `distribution`; and a calculator parser
     that turned junk input into "1 missed call a week".
   - **New:** `/ai-receptionist-nz` (NZ hub), `/tools/missed-call-cost-calculator` (link magnet with a
     shareable URL), the crawler research as a **living data page** (refresh log, CSV distribution,
     freshness check), IndexNow submission on deploy (HTTP 200 for 24 changed URLs), and
     `scripts/vps/sync-tooling.sh` after the deploy gate exposed that host tooling had no publish path.
   - 54 new tests (1413 total at that point; 1419 today), three mutation proofs, deploy verified, live health 46 ok / 0 fail.

## 3. Outstanding — the real worklist

### Operator only (cannot be fixed from this repo)

1. **Stripe charges GST on top of advertised prices.** Measured: Concierge monthly advertises
   USD $250, checkout totals **$287.50**; yearly $2,700 → $3,105; SEO monthly $1,500 → $1,725;
   deposit $1,000 → $1,150. No page mentions GST. Decide: tax-inclusive prices, or change the
   advertised numbers. `site:prices` will fail if GST wording ever appears in the pages instead.
2. **Yearly is contradictory:** `/pricing` sells yearly publicly, while `products.js` keeps the
   yearly link empty. Decide which is true, then align copy and links.
3. **Rotate secrets:** the VPS root SSH key (was readable inside the API image) and the live Stripe
   secret key; rotate the Stripe webhook secret too.
4. **LinkedIn MDP review**, **TikTok token**, **Conrad's snippet**, **Ahrefs mail rule**,
   **replacement Concierge payment link**, **Cloudflare JS detections** — unchanged from the archive.
5. **Inbound SMS has never arrived** (`sms:inbound` warn, 1 paired phone). Needs a text sent to the
   business number.
6. **Decide about the Twenty CRM stack** (`docker compose --profile crm`): run it or retire it.
7. **Search Console and Bing Webmaster:** verify the property and submit
   `https://trendibizz.com/sitemap.xml`. Bing feeds ChatGPT search. Without Search Console there is
   no data on which page is served for which query — the one thing the content work cannot measure
   itself. IndexNow now covers Bing's crawl signal on every deploy, but not the dashboard.
8. **No web analytics** — a click is recorded, the landing visit is not. Needs an account (Plausible
   is the sane pick: cookieless, no consent banner).
9. **Named author / team page** — schema `author` is the Organization until a real named author with a
   bio exists.

### Security / hygiene still open

10. UDP 10000–10099 (RTP) is reachable from the internet; Docker DNAT bypasses ufw and only 5060 is
    filtered. Closing rules are in the header of `scripts/vps/harden_host.sh`.
11. containerd holds ~65 GB of old images (disk 47%). Keep 2–3 `before-*` tags, prune the rest.
12. `/opt/trendi/releases` is world-readable and its test fixtures embed ~32 DSNs and a `whsec_`;
    containers still run as root without `no-new-privileges`.
13. `/var/run/reboot-required` is set. Reboot in a window, then confirm
    `systemctl is-active trendi-sip-firewall.service` is `active` and health is 0 fail.
14. **Commit-time teeth are not installed** — the enforcement catches drift after the fact. A
    `pre-push` hook running the suite plus branch protection on `origin` still needs a decision.
15. **Secrets stay off-repo by design.** `/opt/trendi/shared/api.env` is the source of truth; never
    commit it or copy it into a release tree.

### Unverified product surface (unchanged from the archive)

16. Phone answering end to end: inbound call to the business number, outbound AI callback, transfer
    to the owner, voicemail, and RTP only after item 10.
17. Inbound email and inbound SMS round trips (SMS blocked on item 5).
18. Social publishing to Meta/Google/LinkedIn/TikTok on a real tenant, and the review-request flow.
19. Owner-facing flows only touched by automation: quotes → invoice, designs and CAD uploads,
    marketing-media library, reports export.
20. Anything in §6/§7 of `HANDOFF_ARCHIVE_2026-11-15_1430.md` not named above.

### SEO growth — what the outside audit asked for and what is left

21. **Shareable report pages + "Checked by Trendi" badge** for `/tools/site-check` and
    `/tools/robots-ai-check`. Not built: both tools render results into the DOM as they run, so a
    report needs a stable result record, a URL-encoded store and a page that renders a stored result.
    Half-building it ships broken shared links. **Next:** define the result record → store in the URL
    fragment → `/tools/report/…` renders it → `/brand/checked-by-trendi.svg` badge links to the tool.
22. **City pages (Auckland/Wellington/Christchurch).** Not built, deliberately: the audit's own
    condition is a real case study per city, and there is none published. **Next:** one real case
    study (Pukeko Construction is a live tenant) with real numbers, then one page per city.
23. **Partner co-branded pages.** Needs named partners. **Next:** `website/partners.json` + a generator
    that emits `/partners/<slug>` when the first partner agrees.
24. **"Real questions from callers" data page.** Needs anonymised, consented transcripts from a real
    tenant. Publishing invented "top questions" is the one thing this site says it does not do.
25. **Publishing cadence** — two posts a month on the existing cluster; the first is queued in
    `HANDOFF_ARCHIVE_2026-11-15_1430.md`: "we asked ChatGPT, Perplexity and Google AI Overviews the
    same 12 NZ business questions".
26. **Living data page refresh** — the December 2026 re-fetch is promised on the page and on the
    refresh log. `site:data` warns at 45 days and fails at 120, so it cannot go quiet, but the refresh
    itself is manual: re-run the collection, replace `research/ai-crawler-blocking-2026/data.csv`,
    bump `temporalCoverage` + `dateModified` + the refresh log, then deploy (IndexNow fires itself).
27. **Link earning** — pitch the crawler study to NZ business press; get the two tools listed in NZ
    small-business and agency directories.

### Repository hygiene

28. **Delete `/Users/jo/work-staging/trendibizz-live/site.legacy-20261115`** once another deploy cycle
    proves nothing writes to the old layout.
29. **`scripts/seo/geo-daily.py` — scheduled, and its change detection was broken (fixed 2026-11-16).**
    It now runs on a daily schedule and records Bing visibility. Its `len(text)` fingerprint was
    defeated by Cloudflare's per-request challenge script (`__CF$cv$params`), so every run reported
    all pages changed and re-pinged IndexNow for the whole site; the fingerprint now strips that
    script and hashes the content plus the page's own `dateModified`. Fixed, 3 tests
    (`api/tests/test_geo_daily.py`), mutation-proved, state re-seeded for all 43 URLs — see
    `QA/verification/GEO_DAILY_2026-11-16.md`. **Next:** if IndexNow keeps firing for pages nobody
    edited, suspect a new response-noise source before touching the threshold.

30. **`verify-deploy.sh` is RED right now, by design — two files need an approved deploy.** The box
    (live) is running `tools/missed-call-cost-calculator.html` and `.js` from hand edits made on the
    box on 2026-11-15 that never came back into the repo (manifest commit `08cbdda`). They carry NZ$
    labels and a "GST and tax" note plus GST FAQ, which contradicts the operator decision recorded in
    the health check ("one USD price for everyone, no GST wording anywhere"); the repo is correct, so
    the fix is to publish, not to copy the box back. Nothing was published on 2026-11-16 — the
    scheduled task forbids it without approval. **Next:** `KEY=./Concierge ./scripts/vps/deploy-site.sh`
    (clean tree required), then `verify-deploy.sh` must print `OK: repo and box agree`. Two other
    drift files (`glossary.html`, `research/ai-crawler-blocking-2026.html`) were fixed in the repo
    this session and now match the box.
31. **A `googlebot`-only `noindex` was invisible to the deploy gate until 2026-11-16.** `/glossary`
    and `/research/ai-crawler-blocking-2026` carried `googlebot: noindex` beside `robots: index`, so
    Google was told not to index a 1,043-word guide and the living data page. Fixed in the repo and
    now caught by `site_seo.py`; the live pages already said `index`, so no deploy is needed for that
    pair. See `QA/verification/GEO_DAILY_2026-11-16.md`.

## 4. Next action

**One thing first:** publish the two calculator files with an approved
`KEY=./Concierge ./scripts/vps/deploy-site.sh` — `verify-deploy.sh` is red until then, and live is
advertising NZ$ and GST copy against the USD, no-GST decision.

**Then:** verify `trendibizz.com` in Google Search Console and Bing Webmaster and submit
`https://trendibizz.com/sitemap.xml` (item 7), then fix the Stripe price/tax mismatch (item 1) in the
same sitting — rankings that land on a checkout charging more than the page says convert badly.

The GEO check is green on the technical side and empty on the commercial side: trendibizz.com is in
Bing's index (`site:` at position 10) but absent for all five target prompts. The cheapest next
content move is a dedicated `/ai-receptionist-for-small-business` page — the only one of the five
with no page behind it (item 25 covers the rest of the content list).

The growth work is now self-guarding: the next session that adds a page cannot ship it without a
canonical, a date, a snippet that fits and a sitemap entry, and a data page that goes stale turns the
health check red. That removes the "does anyone watch this?" question from items 21–26; what remains
there is content only the operator can supply.

Before any future session ends, run `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. If it is not
`OK: repo and box agree`, the session is not finished.
