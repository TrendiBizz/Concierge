# Competitor keywords and backlinks — AI receptionist / AI office — 2026-11-25

Ask (Jo): how do we look at competitor sites and backlinks, and make sure we have the same or better
keywords; look at GoHighLevel and others offering an AI office / AI receptionist.
Feature comparison (GHL, Octovox) already exists: `COMPETITOR_GAP_2026-11-12.md`. This record is the SEO side.

## How we look (the repeatable method)
Tool: OpenSEO (self-hosted, project "Trendi", `127.0.0.1:3001`) on a DataForSEO account.
1. **Who really competes in Google** — `find_serp_competitors` on 10 head terms (US, English). Real search rivals are not who we assume.
2. **Their links** — `get_backlinks_overview` per rival: referring domains, trend, top linkers.
3. **Link intersect** — domains that link to 2+ rivals but not us = the realistic target list.
4. **Their keywords** — `get_ranked_keywords` per rival (maxRank 20, minVolume 100), diff against our page map. **BLOCKED today: DataForSEO HTTP 402** on the Labs ranked_keywords endpoint (payment/plan). Not retried. Fix = top up/enable Labs on the DataForSEO account (Jo decision, costs money).
5. **Our own position** — weekly SERP tracker (`~/OpenBot/Shared/trendi-seo/terms.csv`, `monitor/serp_check.py`) + GSC; loop is in `docs/SEO_GROWTH_ENGINE.md`.
Credits: SERP-competitors + 6 backlink overviews only (small). Nothing spent on the 402 calls.

## Who ranks (US Google, 10 head terms) — evidence
| Domain | Terms of 8-10 ranked | Notable positions |
|---|---|---|
| ringcentral.com | 6 | "ai receptionist" #1, "ai answering service" #3 |
| goto.com | 5 | "ai receptionist for small business" #1 |
| withallo.com | 7 | "best ai receptionist" #1, "missed call text back" #2, "ai receptionist cost" #3 |
| smith.ai | 7 | "virtual receptionist" #3 |
| myaifrontdesk.com | 7 | "ai receptionist cost" #4 |
| upfirst.ai, goodcall.com, dialzara.com, heyrosie.com, synthflow.ai, cloudtalk.io | 3-8 | mid/low pages |
| **gohighlevel.com** | **not in top 25** | Not among the 25 domains with most keyword overlap on these 10 terms (list was sorted by keyword count). GHL is a platform competitor, not a head-term SERP rival; its AI Employee pages rank on its own brand terms. |
| trendibizz.com | 0 | excluded from query; tracker shows nothing in top 10 NZ (2026-11-09). |
Winners are not all small AI startups: the big telecoms (RingCentral, GoTo) and review/listicle sites (smash.vc #1-#4, technologyadvice.com) take the top. "Best ai receptionist" is a listicle SERP: we win it by being IN the lists, not by our own page.

## Backlinks (scale gap)
| Site | Referring domains | Domain rank | Trend (12 mo) |
|---|---|---|---|
| gohighlevel.com | 26,528 | 75 | flat-ish, 1.2M links, mostly affiliate/tutorial/network sites |
| smith.ai | 4,305 | 52 | +38% |
| goodcall.com | 3,836 | 50 | +37% |
| myaifrontdesk.com | 2,637 | 60 | +200% (rank 43 to 60) |
| withallo.com | 913 | 40 | **x5 in 12 months (174 to 913)** |
| **trendibizz.com** | **75** | **18** | 44 to 75; Sept spike 261 then fell; 17 broken links; 23 of 103 links from one site |
Read: we are 12x smaller than the smallest rival that matters (Allo), and Allo shows the playbook works in a year without ad spend: it grew by getting listed everywhere below.

## Link intersect: sites linking to several rivals (our target list)
Link to 2+ of Goodcall / Smith.ai / Allo / MyAIFrontDesk (read by eye from the top-100 linker lists, so a longer tail is likely missed): businessaifinder.com, tryanswrr.com, vocenya.com, oppalerts.com, seektool.ai, aiqlabs.ai, getcovedesk.com, shouldiuse.io, vicem.ai, calltrin.com, lobbystack.com, solwees.ai, tradeswithai.com, futurocorp.com, vantaweb.io, thetoolregister.com, dooza.ai, usetwine.com, saashub.com, worldmetrics.org, zipdo.co, statpit.com, wifitalents.com, agenticindex.io, voiceagentscout.com, insertchat.com, eesel.ai, leapscopeai.com, nucamp.co, receptionistindex.com, thefrontdeskindex.com, toolify.ai, aitoolnet.com. Single-rival, worth a look: answeringservicequotes.com (Smith.ai), receptionistratings.com (Allo).
- **Already linking to us:** thefrontdeskindex.com (23 links, first seen 2026-11-20, spam score 19). It also links Smith.ai, Allo, MyAIFrontDesk, Goodcall, so it is a ranking/index page: check how we are listed and claim/correct it.
- Types: AI-tool directories (free submit), "receptionist index/ratings" listicles (outreach for inclusion), stat-aggregator sites (worldmetrics/zipdo/wifitalents: low value, skip), trades-AI sites (tradeswithai.com: matches our builders page).
- Avoid: spam-score 25+ with rank 0 networks (klobyz, sca-if, eurodmcorp...) that appear on every rival — a shared PBN footprint, not a model to copy.
- Our existing queue: `scripts/seo/backlinks/prospects.csv` (24 rows, 0 links claimed). None of the domains above are in it yet except via the generic "global directory" rows: add them.

## Keyword coverage: our pages vs where rivals rank
| Term (US head term) | Our page today | Verdict |
|---|---|---|
| ai receptionist / for small business | `/` , `/concierge`, `/ai-office` | covered; no dedicated `/ai-receptionist` page (planned 2026-11-11, never built) |
| ai receptionist cost | `/ai-office-cost` | covered |
| virtual receptionist | `/virtual-receptionist` | covered, thin vs Smith.ai |
| missed call text back | `/missed-call-text-back` | covered (Allo #2, so quality bar is high) |
| ai answering service | `/ai-answering-service-vs-human` only | **gap: no money page** |
| ai phone answering | none | **gap** |
| best ai receptionist | `/best-ai-office` | covered by us; real route is third-party lists |
| comparison pages (X vs GoHighLevel / Smith.ai / Goodcall / Allo, "X alternative") | only `/trendi-vs-otterly|profound|firstindex` (SEO tools, different product) | **gap: none for receptionist rivals** |
| "gohighlevel alternative / cheaper than GoHighLevel" | none | **gap** (README already says "de-bloated alternative to GoHighLevel") |
| industry pages | builders, clinics, real estate, NZ | covered; add trades subtypes (plumbers, electricians) |
Noted but not changed: `pricing.html` title says "from USD $199 a month" while `SEO_KEYWORDS_2026-11-11.md` and homepage copy cite USD $400; reconcile before more pages are written.

## Recommended actions (not yet done)
1. **Jo decision:** top up / enable DataForSEO Labs to unlock `ranked_keywords` (real keyword-by-keyword diff of Allo, Smith.ai, Goodcall, GHL). Without it we rely on SERP samples.
2. Build 3 pages: `/ai-answering-service`, `/ai-phone-answering`, `/gohighlevel-alternative` + `/trendi-vs-goodcall|smith-ai|allo` comparison set (honest, sourced, with `site_seo.py check` gate).
3. Submit to the ~12 free AI directories in the intersect list; pitch inclusion to receptionistindex/ratings, businessaifinder, thefrontdeskindex.
4. Fix our 17 broken inbound links (301 or restore the pages) — free authority.
5. Add the intersect domains to `prospects.csv`; run `backlink_engine.py report` weekly; re-pull `get_backlinks_overview` monthly for the same 6 domains to track the gap.
6. Re-run step 1 monthly with the same 10 terms; add NZ-market terms (locationCode 2554) once volume data is available.

## Limits (honest)
- Ranked-keyword lists not obtained (402). Keyword verdicts above come from SERP positions for 10 terms and our page titles, not full keyword exports.
- Backlink counts are DataForSEO estimates; "rank" is its own scale, not Moz DA.
- US market used for rivals (global products); our tracker is NZ. Different SERPs.
- No page, copy or link changes were made by this record.
