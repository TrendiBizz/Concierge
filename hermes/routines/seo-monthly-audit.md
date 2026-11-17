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

Save to `/opt/data/.workwatch/reports/hermes/seo-engine/<date>-seo-monthly-audit.md` and
update `latest.md`.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/seo-engine/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/seo-engine/<YYYY-MM-DD>-seo-monthly-audit.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# seo-monthly-audit — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/seo-engine/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
