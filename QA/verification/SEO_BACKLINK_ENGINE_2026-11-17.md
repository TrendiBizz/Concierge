# SEO growth engine + Concierge ranking baseline — 2026-11-17

## What Jo asked

"how we have an SEO engine that is continuously working to find how we improve our
rankings and ensuring we keep Concierge as high in rankings as we can… a clear
backlink/seo ranking mechanism… critical piece of missing structure."

## What was actually there

- A good daily technical/search monitor and weekly DataForSEO/SERPer cycle.
- 17 tracked terms, all SEO-agency terms. **Zero Concierge/receptionist terms.**
- No backlink prospects, no outreach ledger, no link verification.
- Latest SERP data (2026-11-09) had Trendi outside the top 10 for every tracked term.
- GSC last 7 days: 0 clicks, 92 impressions (handoff 2026-11-17g).

So the engine was watching the wrong product cluster and had no authority-building loop.

## What was built

1. `docs/SEO_GROWTH_ENGINE.md` — the operating model:
   measure → decide/improve pages → earn links → verify → weekly scorecard.
   Includes target tiers, quality rules, 90-day plan and stop rules.
2. `scripts/seo/backlink_engine.py` — queue, report and live-link verification.
3. `scripts/seo/backlinks/{prospects,outreach,links}.csv` — 24 initial prospects,
   empty outreach/link ledgers, every row with a next action.
4. `scripts/seo/backlinks/pitches/ai-crawler-study.md` — first editorial pitch.
5. `scripts/seo/test_backlink_engine.py` — 4 tests, no network.
6. 12 Concierge terms added to the live tracker (`~/OpenBot/Shared/trendi-seo/terms.csv`)
   and mapped to existing pages.
7. `monitor/serp_check.py` widened and fixed:
   - `CORE_MAX 12 → 9`, `NZ_MAX 4 → 16`; plan is 52 credits/week, under the 60 cap.
   - Continuity bug: `_previous_terms()` returned every term for both markets, so the
     frozen list kept re-selecting generic terms and squeezed Concierge out. It now
     returns separate core and NZ sets.

## Proof

```
$ python3 scripts/seo/backlink_engine.py report
Prospects: 24 total; active 24
Tier 1: 8 · Tier 2: 13 · Tier 3: 3
Claimed links: 0

$ python3 -m unittest scripts/seo/test_backlink_engine.py
Ran 4 tests ... OK

$ python3 scripts/seo/site_seo.py check
OK: 46 pages — canonical, robots, h1, snippet, dates, links, sitemap and IndexNow key all agree
```

Live rank baseline (2026-11-17, Google NZ, 25 terms, 24 Serper credits):

```
terms_checked 25 · ok 25 · trendi_in_top10 [] · previous_run 2026-11-09
credits before 2230 · after 2206 · used 24
```

All 12 Concierge terms are now checked; none is in the top 10:

| Term | Page | Position |
|---|---|---|
| ai receptionist | `/ai-receptionist` | not in top 10 |
| ai receptionist nz | `/ai-receptionist-nz` | not in top 10 |
| virtual receptionist nz | `/virtual-receptionist` | not in top 10 |
| answering service nz | `/ai-answering-service-vs-human` | not in top 10 |
| after hours answering service | `/after-hours-answering` | not in top 10 |
| missed call text back | `/missed-call-text-back` | not in top 10 |
| ai receptionist for builders | `/ai-receptionist-builders` | not in top 10 |
| ai receptionist for real estate | `/ai-receptionist-real-estate` | not in top 10 |
| ai receptionist for clinics | `/ai-receptionist-clinics` | not in top 10 |
| ai receptionist cost | `/ai-receptionist-cost` | not in top 10 |
| best ai receptionist | `/best-ai-receptionist` | not in top 10 |
| how does an ai receptionist work | `/how-does-an-ai-receptionist-work` | not in top 10 |

Baseline file: `~/OpenBot/Shared/trendi-seo/monitor/serp/nz/2026-11-17.csv`.

## Cause / fix / proof for the continuity defect

- **Cause:** `_previous_terms()` returned one set containing both `global` and `nz`
  terms. `select_terms()` passed that set to both `_round_robin` calls, so the NZ
  selection kept up to 12 previous terms — including terms that were only core terms —
  leaving one or zero slots for the new Concierge cluster.
- **Fix:** return `(core_terms, nz_terms)` and pass each set only to its own selection.
  Reset the stale frozen list once (`monitor/serp_terms.json` backed up), then reselect.
- **Proof:** before the fix the rebuilt list had 1/12 Concierge terms; after it has
  12/12 and the plan is 52 credits. The baseline run checked all 25 terms with 0
  failures.

## First outreach sent (2026-11-17 22:18 NZDT)

Jo approved sending the first five after seeing the drafts. Four were accepted by the
Brevo SMTP relay from `admin@trendibizz.com`:

| Prospect | Address | Subject |
|---|---|---|
| NZ Entrepreneur | editor@nzentrepreneur.co.nz | Data: how 100 SaaS sites treat AI crawlers |
| TechDay | editors@techday.com | New Zealand study: AI crawler access on 100 SaaS sites |
| BusinessDesk | info@businessdesk.co.nz | Data: only 2 of 94 SaaS sites block a major AI crawler |
| interest.co.nz | news@interest.co.nz | Data: AI crawler access across 100 SaaS sites |

The fifth, Search Engine Journal, is a web form protected by Cloudflare Turnstile and
was **not** submitted. Its exact text is in
`scripts/seo/backlinks/outbox/05-search-engine-journal.txt`. Follow-up date for the four
emails: 2026-11-24. All sends and statuses are in `outreach.csv` and `prospects.csv`.

## What is not done

- No outreach has been sent. The first 8 tier-1 prospects still need named contacts.
- No backlink has been earned yet; `links.csv` is empty by design.
- No link data from GSC/Bing is recorded yet. Bing `GetLinkCounts` returns an empty
  list for the domain today; GSC Links needs a manual export.
- The weekly Hermes cycle does not yet read the backlink report. That is the next
  wiring step, not a reason to claim the loop is complete.
- The 12 Concierge pages need page-level work (titles, proof, internal links) before
  links alone can move them. The design doc makes that Loop B, not a link-only bet.
