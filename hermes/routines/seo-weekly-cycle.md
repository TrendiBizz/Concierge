# Routine: Weekly SEO cycle (Trendi)

- Profile: `seo-engine`
- Schedule: `0 8 * * 1` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/seo-weekly-cycle.md`
- Status: active
- Approval: audits only; site changes go through the gate after Jo's yes

## Procedure

Weekly SEO cycle for trendibizz.com (and any signed client sites). Global
English-speaking audience; NZ is one market. Read `~/jo-brain/AGENTS.md` and
`~/jo-brain/trendi/` notes first.

1. **Fresh data.** Pull from the connected free sources: Search Console queries,
   positions, countries, URL Inspection; Bing Webmaster keyword stats and AI
   performance; Brave Autosuggest. Reuse the daily monitor history in
   `~/OpenBot/Shared/trendi-seo/monitor/history/`.
2. **Rank check.** Check the Serper balance with the free `/account` call, run
   `monitor/serp_check.py --dry-run`, confirm the estimate is `<= 60` credits, then
   run live (Google US, UK, AU, NZ; core terms in all four, NZ terms in NZ only).
   Read `monitor/serp/<date>.by_market.json` and report by market, never blended.
   Do not reselect terms unless the quarterly rebuild says so.
3. **DataForSEO** (Jo approved 1 Nov; cap **$0.08/week**, trial credit only, never
   top up, no other paid tools). Run `dataforseo/weekly.py --dry-run`, confirm
   `<= $0.08`, then live. It skips if the balance is under $0.10 or the last run was
   under 6 days ago, logs to `dataforseo/spend.csv`, and pulls volumes for
   US/GB/AU/NZ plus a live Google check (organic + async AI Overview) for 5 US money
   terms. Warn Jo if the balance nears $0.10.
4. **Audit.** `cd ~/OpenBot/Shared/trendi-seo/audits && ./audit all` (never
   `--submit`). Read `out/<date>/crawl_issues.csv` (high/medium), `psi.csv`,
   `gsc_countries.csv`.
5. **Terms.** Refresh `terms.csv` (no source, no term).
6. **Change verification.** Check `~/OpenBot/Shared/trendi-seo/changes.csv` **and**
   the OpenBot deploy rows in `~/OpenBot/Shared/trendi-site/seo/changes.csv`: indexed
   within 14 days, impressions by week 4–8, stop-loss week 8.
7. **Actions.** Pick the top 3. Site-file changes are applied through the Trendi
   deploy gate; copy and new pages become briefs under `trendi-seo/briefs/`.
   Suggest 2–3 short-video ideas from real search wording in `video_ideas.csv`
   (nothing posted without Jo's OK). Pending: check which page the `otterlyai` query
   lands on and tighten its title/meta (as a gated fix or a brief).

## Report

Write a short scorecard: indexed pages, impressions, clicks, average position,
top-10 count per market, AI-panel trend, DataForSEO money-term ranks + AI Overview
citations, spend and balance — each vs last week, `no data yet` where true. Then a
friendly 5-line report: where Trendi shows in US/UK/AU/NZ, GSC impressions by
country, what shipped, what is next, what needs Jo's yes. Say what to reconnect if a
source fails auth.

Never invent numbers or promise rankings; NZ English.

Save to `/opt/data/.workwatch/reports/hermes/seo-engine/<date>-seo-weekly-cycle.md` and update
`latest.md`.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/seo-engine/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/seo-engine/<YYYY-MM-DD>-seo-weekly-cycle.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# seo-weekly-cycle — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/seo-engine/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
