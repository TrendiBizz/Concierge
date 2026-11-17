# SEO growth engine — rankings and backlinks

Status: design + initial pipeline, 2026-11-17. This is the missing structure Jo named:
one loop that continuously measures rankings, decides what to change, earns links, and
proves what moved.

**This is a mechanism, not a promise of rankings.** Google does not guarantee positions.
Links are one signal among many; the loop below makes the work visible and testable.

## 1. The honest baseline

From the data already on the Mac (2026-11-17):

| Measure | Current | Source |
|---|---|---|
| Indexable pages | 46 | `python3 scripts/seo/site_seo.py check` |
| Tracked search terms | 25: 9 core, 4 existing NZ, 12 Concierge (all NZ) | `~/OpenBot/Shared/trendi-seo/terms.csv` |
| Concierge/receptionist terms tracked | **12** (added 2026-11-17) | same |
| Trendi in the top 10 for tracked terms | **none** (latest run 2026-11-09) | `monitor/serp/*/*.csv` |
| Google clicks, last 7 days | **0** | GSC, recorded in handoff 2026-11-17g |
| Google impressions, last 7 days | **92** | same |
| Backlink pipeline | **none** | this repo before today |

So the problem is not that the SEO monitor is broken. It is that the site is early,
the monitor watches the wrong product cluster, and there is no link-earning machine.

## 2. What the engine owns

Three loops, one weekly scorecard.

### Loop A — Measure

- **Daily** (already exists): site health, sitemap/robots/llms, GSC/Bing, CWV, de-index.
- **Weekly** (already exists, extend): positions by market, GSC clicks/impressions/CTR,
  top-10 count, page-level winners/losers, referring domains, new/lost links.
- **Monthly** (already exists): technical audit, content decay, cannibalisation, schema.

### Loop B — Decide and improve pages

- One keyword → one page. No two pages targeting the same intent.
- Concierge gets its own cluster: 12 NZ commercial terms, tracked weekly.
- Every page gets one primary term and 2–4 supporting terms.
- Change one thing at a time: title/H1, intro, proof, internal links, schema, or a new
  section. Record it in `~/OpenBot/Shared/trendi-seo/changes.csv`.
- Stop rules: 8 weeks with no movement → rewrite the page or change the target; 12 weeks
  → merge or remove. Do not keep “optimising” a page that cannot win.

### Loop C — Earn links

Links are earned with assets someone would cite, not by mass directory submission.

**Assets we can pitch now**

1. **AI crawler study** — 100 well-known B2B/SaaS sites, robots.txt and llms.txt,
   reproducible method and data. This is the strongest press asset.
2. **Robots.txt AI checker** — a working free tool at `/tools/robots-ai-check`.
3. **Site checker** — a working free tool at `/tools/site-check`.
4. **Pukeko Construction case study** — once the numbers and permission are confirmed.
5. **NZ AI receptionist pricing/data page** — once there is real data, not invented.

**Target tiers**

| Tier | What | Examples | Link value |
|---|---|---|---|
| 1 | NZ business/tech press and industry bodies | NZ Entrepreneur, TechDay, CIO NZ, Idealog, BusinessDesk, interest.co.nz, Master Builders, REINZ | Editorial, brand, referrals |
| 2 | Reputable directories and tool lists | Yellow NZ, Neighbourly, KiwiSaaS, Clutch, DesignRush, GoodFirms, Sortlist, Semrush Agencies, Product Hunt, AlternativeTo, SaaSHub, Futurepedia | Citations, discovery, some followed links |
| 3 | Partners and communities | Pukeko, web studios, accountants, chambers, meetups | Relevant editorial/partner links |

**Cadence (weekly, 2–3 hours)**

1. Research 10 new prospects; add to `prospects.csv`. Only real, relevant sites.
2. Choose 5 with a specific reason to link (asset, data, partner, local angle).
3. Write one personalised pitch per prospect. No template blast. Do not send without Jo's
   approval for the first 4 weeks; after that, only pre-approved templates.
4. Follow up once after 5 working days. Then stop.
5. Record every send and reply in `outreach.csv`; never invent a contact or a reply.
6. Verify every claimed link with `backlink_engine.py verify`. A link is not “won” until
   the source URL returns 200 and contains the target.
7. Report one number: **new live referring links this week**. Not “emails sent”.

**Quality rules (from Google's spam policies)**

- No paid links that pass ranking signals, no link exchanges at scale, no PBNs, no
  automated blast, no fake directories.
- A directory must be edited, relevant, and have real users. If it accepts every site
  instantly, it is not worth the submission.
- Guest posts only where the audience is real and the piece would be published anyway.
- Use `rel="sponsored"`/`nofollow` correctly on any paid or affiliate placement.
- Never fabricate a case study, a review, a rating, or a client.

## 3. The Concierge keyword cluster

These are the first 12 terms. They are NZ-only because the buying intent is local.
Each maps to an existing page; no new page is created until the page has proof.

| Term | Page | Intent |
|---|---|---|
| ai receptionist | `/ai-receptionist` | commercial |
| ai receptionist nz | `/ai-receptionist-nz` | commercial |
| virtual receptionist nz | `/virtual-receptionist` | commercial |
| answering service nz | `/ai-answering-service-vs-human` | commercial |
| after hours answering service | `/after-hours-answering` | commercial |
| missed call text back | `/missed-call-text-back` | commercial |
| ai receptionist for builders | `/ai-receptionist-builders` | commercial |
| ai receptionist for real estate | `/ai-receptionist-real-estate` | commercial |
| ai receptionist for clinics | `/ai-receptionist-clinics` | commercial |
| ai receptionist cost | `/ai-receptionist-cost` | commercial |
| best ai receptionist | `/best-ai-receptionist` | commercial |
| how does an ai receptionist work | `/how-does-an-ai-receptionist-work` | informational |

The existing SEO-agency terms stay. The tracker is widened to 16 NZ slots (12 Concierge +
4 existing) and 9 core terms; the weekly ceiling is 52 credits, under the 60 cap.

## 4. Scorecard (the only numbers that matter)

Weekly, by market, never blended:

- **Rankings:** top-10 count, top-3 count, average position for tracked terms, biggest
  movers up/down. A blank position means “not in top 10”, not zero.
- **Search demand captured:** GSC clicks, impressions, CTR, average position; 7-day and
  28-day windows.
- **Authority:** live referring domains, new links, lost links, links by target page.
- **Work:** pages changed, pieces published, prospects contacted, replies, placements.
- **Quality:** indexed pages, CWV, crawl errors, canonical/robots failures.

The weekly report must say “no data yet” where a source has not run. It must not turn a
missing number into a zero or a win.

## 5. 90-day plan

**Days 1–14 — instrument**

- Add the 12 Concierge terms to the tracker; run one live baseline.
- Create the backlink pipeline (this repo) and a first list of 25 prospects.
- Get a GSC links export (manual, Search Console → Links) and a Bing link count as the
  baseline. Record them; do not guess.
- Pick the first 3 assets to pitch.

**Days 15–30 — first links**

- Pitch the AI crawler study to 8 NZ/industry publications and 2 global SEO publications.
- Submit the two tools to 10 reputable directories/tool lists.
- Ask Pukeko for permission to publish the case study; if yes, write it.
- Target: 3 live, relevant referring links. Quality over count.

**Days 31–60 — clusters**

- Publish two pieces on the Concierge cluster: “AI receptionist cost NZ” and “missed call
  text back: what actually happens”.
- Add internal links from the home page and pricing page to the Concierge cluster.
- Refresh the AI crawler study with the December re-fetch; pitch the refresh to the same
  publications (“updated data” is a second story).
- Target: 6 live links; first top-10 position for one long-tail Concierge term.

**Days 61–90 — compounding**

- One partner page or co-branded case study.
- One local chamber/industry association listing or talk.
- Monthly content refresh; kill or merge pages that cannot win.
- Target: 10 live links; 3 top-10 Concierge terms; measurable GSC clicks, not just
  impressions.

## 6. Roles and guardrails

- **Hermes `seo-engine`** runs the daily monitor, weekly cycle and monthly audit. It
  proposes; it does not send outreach or publish without Jo.
- **The Mac session** owns the backlink CSV, the outreach drafts, and the deploy gate.
- **Jo** approves: the first outreach batch, any paid placement, any case study, any new
  page that makes a claim about a customer.
- **Never** buy links, mass-submit, fake a review/rating/client, or publish invented data.

## 7. Files and commands

- `scripts/seo/backlinks/prospects.csv` — every target, status and next action.
- `scripts/seo/backlinks/outreach.csv` — every contact, send, reply, follow-up.
- `scripts/seo/backlinks/links.csv` — every claimed link, verified.
- `scripts/seo/backlink_engine.py queue` — this week's shortlist.
- `scripts/seo/backlink_engine.py report` — pipeline and live-link scoreboard.
- `scripts/seo/backlink_engine.py verify` — check claimed links are still live.

The existing rank tracker stays where it is; this engine feeds it and reads its output.
