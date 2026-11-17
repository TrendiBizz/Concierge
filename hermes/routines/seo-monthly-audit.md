# Routine: Monthly SEO audit (Trendi)

- Profile: `seo-engine`
- Schedule: `0 9 1 * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/seo-monthly-audit.md`
- Status: active
- Approval: audits only; copy and new pages are briefs

## Procedure

Monthly audit and system retro. Read `~/jo-brain/AGENTS.md` and `~/jo-brain/trendi/`
notes.

1. Run:

   ```bash
   cd ~/OpenBot/Shared/trendi-seo/audits && ./audit all
   ./audit gsc --days 28
   ./audit psi --strategy both
   ```

   Never `--submit`. Compare with last month's `out/<date>/`.
2. Check sitemap, robots, schema and `llms.txt`.
3. Re-run:

   ```bash
   /opt/data/venvs/trendi-seo/bin/python ~/OpenBot/Shared/trendi-seo/audits_global/nz_wording.py
   ```

   Home, pricing and about stay global; NZD/GST lines are expected there.
4. Refresh Brave Autosuggest per country (us, gb, au, nz) and add new terms with a
   market tag.
5. Start this month's 25-prompt AI-visibility panel with
   `.venv/bin/python ai_panel/run_panel.py` (about 25 Serper credits; 2 days on the
   Gemini free tier, the daily monitor finishes it). Skip if the latest run is within
   10 days and report on that one.
6. Export GSC and Bing AI reports if available. Prune dead terms from `terms.csv`
   (back up first to `backups/`).
7. In Jan/Apr/Jul/Oct, rebuild the term list and reselect rank terms with
   `monitor/serp_check.py --reselect`.
8. Copy and new pages become briefs.
9. Short retro of the whole system (SEO, site, monitor thresholds, Serper balance,
   video pipeline `~/OpenBot/Shared/trendi-studio/brand_pipeline`, social, coverage
   plan): what worked, what did not, **exactly one** process change, appended to
   `~/OpenBot/Shared/trendi-seo/retro.md`.

## Report

Findings by market, the one change, what needs Jo's yes. Never invent numbers or
promise rankings; NZ English.

Save to `~/.workwatch/reports/hermes/seo-engine/<date>-seo-monthly-audit.md` and
update `latest.md`.
