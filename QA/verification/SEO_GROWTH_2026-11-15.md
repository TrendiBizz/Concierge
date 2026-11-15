# SEO growth implementation — 2026-11-15

**Context.** An outside audit of `trendibizz.com` concluded that the technical side was already
sound (unique titles, canonicals, structured data, 404s, a 40-URL sitemap, sane `robots.txt`) and
that the problem was off-site: nobody links to the site, and it competes head-on with funded brands
in "AI receptionist" and "AI visibility". It proposed seven things that are not the usual playbook:
win one small market first (NZ), make the free tools earn links, publish one living data page, use
real questions from the product, grow through partners, build tools people use before they buy, and
keep the ranking with IndexNow plus a post-deploy guard and a quarterly refresh.

This record covers what was implemented, what was deliberately not built, and why.

---

## 1. The guard first: a technical SEO contract, enforced at deploy

The audit's premise ("the technical side is already good") was **not** true in the repository, and
nothing watched it. `scripts/seo/site_seo.py` now defines the contract and
`scripts/vps/deploy-site.sh` refuses to publish when it is broken. The live health check gains
`site:seo` and `site:data`.

**Defects found and fixed on the first run (every one was live):**

| # | Defect | Cause | Evidence |
|---|---|---|---|
| 1 | 21 AppleDouble `._*` files were committed to the web root (19 HTML, 1 CSV, 2 PNG) | macOS resource forks added to git; the deploy excluded them from rsync, so they were invisible on the box but permanent in the repo | `git ls-files website \| grep '/\._'` → 21; files untracked, deleted, `._*` added to `.gitignore` |
| 2 | `/glossary` — a 1,043-word guide — was `noindex` **and** absent from the sitemap | A `noindex` from the Oct 2026 "remove NZ targeting" commit was never revisited, and the sitemap was hand-maintained | Now `index, follow`, in the sitemap, linked from `/ai-visibility`, `/generative-engine-optimization` and `llms.txt` |
| 3 | 11 pages published no `dateModified` at all (`/`, `/about`, `/concierge`, `/contact`, `/privacy`, `/terms`, `/seo`, `/virtual-receptionist`, `/concierge-start`, `/ai-answering-service-vs-human`) | Structured data was added page by page; these were missed | Dates inserted from the real last change (2026-11-15); the check now fails when a page has none |
| 4 | The sitemap disagreed with the pages in 13 places, carried a `<url>` line with broken indentation, and `/concierge-start` had no `lastmod` | Hand-edited XML | `sitemap.xml` is now generated from the pages (`site_seo.py sitemap --write`); lastmod is copied from each page's structured data |
| 5 | `/research/ai-crawler-blocking-2026` — the site's only original data — was linked from **nowhere** | Published, then never linked | Now linked from `/ai-visibility`, `/robots-txt-ai-search`, `/llms-txt`, `/generative-engine-optimization`, `/seo`, `/tools/site-check`, `/tools/robots-ai-check`, `llms.txt`; a guard fails if a Dataset page has fewer than 3 inbound links |
| 6 | The published Dataset described no download, so the CSV was only discoverable by scrolling | Schema was written before the CSV mattered | `distribution` (`text/csv`, `contentUrl`) added, plus `isAccessibleForFree` |
| 7 | The calculator's number parser turned junk into a number: `?missed=<script>alert(1)</script>` became **1 missed call a week** | `parseFloat` over a string with non-digits stripped — "mine the digits" | Rewritten as a strict parse with an explicit decoration allowlist; the test was red before the fix and is green after |

**Tests: 54 new, 1413 total passing.** `api/tests/test_site_seo.py` (41) covers every rule above on
synthetic site trees *and* the real tree; `api/tests/test_missed_call_calculator.py` (13) runs the
shipped JavaScript under Node so the test exercises the code the browser runs.

Mutation proofs actually run, not asserted:

- Deleted `User-agent: GPTBot / Disallow: /` from `robots.txt` → `test_the_real_site_tree_passes_its_own_contract` **FAILED**; restored → passed.
- Removed the `site_seo.py check` line from `deploy-site.sh` → `test_the_deploy_runs_the_contract_before_publishing_and_pings_afterwards` **FAILED**; restored → passed.
- Editing the research page's date without regenerating the sitemap → the check failed immediately with `sitemap lastmod for … is 2026-11-04, page says 2026-11-15` (this happened live during the work and is the guard working).

**IndexNow.** `scripts/seo/indexnow.py` existed but was called by nothing and sent one request per
URL. It is replaced by `site_seo.py ping`: one batched POST, key read from `website/indexnow-key.json`,
and only the pages whose source changed since the commit that was previously live (read from the
deploy manifest on the box). It runs after `verify-deploy.sh`, and a ping failure never fails a
deploy.

## 2. What was built for each idea

| Audit idea | What exists now | Where |
|---|---|---|
| Win one small market first (NZ) | `/ai-receptionist-nz` — an NZ hub written to NZ realities (after-hours enquiries, on-site callers, the daylight-saving configuration trap, Privacy Act 2020 obligations that stay with the customer), with `areaServed` for NZ and the three main centres, linked from the five page cluster and `llms.txt`. Existing pages were **not** flipped to NZ-first: the site deliberately sells in USD worldwide, and that positioning decision is the operator's, not a content edit | `website/ai-receptionist-nz.html` |
| Free tools earn links | `/tools/missed-call-cost-calculator` — new link magnet with a shareable URL (the numbers live in the query string, no account, nothing sent to the server), a documented formula, and an explicit "what this leaves out" section | `website/tools/missed-call-cost-calculator.{html,js}` |
| One living data page | The crawler research is now a living page: fixed address, visible "refreshed monthly", a refresh log with versions, `distribution` + CSV, `dataset` discoverability guard, and `site:data` health check that warns at 45 days and fails at 120 | `website/research/ai-crawler-blocking-2026.html` |
| Keep the ranking | Deploy gate + IndexNow + `site:seo` (robots policy, every sitemap URL 200/canonical/indexable, IndexNow key) + `site:data` freshness | `scripts/seo/site_seo.py`, `scripts/vps/healthcheck.py` |
| Real questions from the product | **Not built** — needs real, consented call data from a live tenant | see §3 |
| Partners | **Not built** — needs real partner businesses | see §3 |
| Quarterly refresh | Guarded rather than promised: a page's `dateModified` and its visible "last updated" line must agree, and the data page's age is measured | `site_seo.py`, `site:data` |

## 3. Deliberately not built, and what unblocks it

1. **Shareable report pages for `/tools/site-check` and `/tools/robots-ai-check`.** The badge-and-report
   idea needs the two existing tools to serialise their result state into a URL. Both render results
   into the DOM as they run (`site-check.js` fetches its own API, `robots-ai-check.js` fetches the
   target's `robots.txt`), so a report page is a real feature, not a template: it needs a stable result
   shape, a server-side or hash-encoded store, and a page that renders a result without re-running the
   check. Half-building it would ship broken shared links. **Next step:** define the result record,
   store it in the URL fragment, add `/tools/report/…` that renders a stored record and a
   `/brand/checked-by-trendi.svg` badge that links to the tool — then every use creates a page worth
   linking to.
2. **City pages (Auckland/Wellington/Christchurch).** The audit's own condition is "only markets that
   can be supported with a real case study". There is no published case study on the site yet, so a
   city page today would be the templated copy the audit warned against. **Next step:** one real case
   study (Pukeko Construction is the obvious candidate — it is a live tenant) and then one page per
   city with that customer's actual numbers.
3. **Partner co-branded pages.** Needs named partners. **Next step:** add `website/partners.json` and a
   generator that emits `/partners/<slug>` from data, when the first partner agrees.
4. **"Real questions from callers" data page.** Needs anonymised, consented transcripts from a real
   tenant. Publishing invented "top questions" would be the one thing this site says it does not do.
5. **Search Console / Bing Webmaster verification.** Operator-only (needs the account). The site now
   submits itself to IndexNow on every deploy, which covers Bing's side of the crawl signal without
   the dashboard.

## 4. Verification

- Full suite: **1413 passed** (`cd api && TEST_DATABASE_URL=… python3 -m pytest -q`).
- `python3 scripts/seo/site_seo.py check` → `OK: 45 pages — canonical, robots, h1, snippet, dates,
  links, sitemap and IndexNow key all agree`.
- Deploy and live health: see the deploy section below.

## 5. Deploy record

_(appended after `deploy-site.sh` and `verify-deploy.sh` were run)_
