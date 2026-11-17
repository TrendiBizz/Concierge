# Routine: Daily site + search monitor (Trendi)

- Profile: `seo-engine`
- Schedule: `30 7 * * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/seo-daily-monitor.md` (Grok SEO Engine
  07:30 copy paused 2026-11-06; this is the Workwatch text)
- Status: active
- Approval: read-only; no site changes

## Procedure

Daily lean monitor for trendibizz.com.

1. Run:

   ```bash
   cd ~/OpenBot/Shared/trendi-seo && \
     /opt/data/venvs/trendi-seo/bin/python monitor/daily_monitor.py
   ```

2. Read its JSON verdict: `status` is `quiet`, `alert` or `win`, plus `items`.
3. If the latest AI-panel run in `~/OpenBot/Shared/trendi-seo/ai_panel/runs/` has
   unanswered prompts (Gemini free tier is about 20 requests a day), resume it once:

   ```bash
   /opt/data/venvs/trendi-seo/bin/python ai_panel/run_panel.py --date <that run's date>
   ```

   No Serper credits; it stops itself at the daily limit. Only do this if
   `~/OpenBot/Shared/trendi-seo/CUTOVER.md` still marks this routine CUT OVER.
4. No extra research or crawling.
5. If a script is missing or crashes, look once, fix only the obvious script bug,
   re-run once. Do not redesign it.

## Verdict handling

- **quiet** — nothing to Jo.
- **alert** — page down, robots/sitemap/llms.txt changed or invalid, crawl errors up,
  de-index, CWV/SEO score slipping, a data source or key failing 2+ days, Serper
  credits low.
- **win** — first impressions/clicks, a new query, a meaningful impressions/position
  jump, a newly indexed page, or Trendi mentioned in the AI panel.

For an alert or a win, write a report in 1–3 plain NZ English sentences: what
happened, why it matters, one next step. Never invent numbers.

## Output

Quote the verdict's `status`, `items`, `run_at` and `seconds` exactly in the report. If
`status` is `alert` or `win`, quote every item with its number. A report that says
"all normal" without the verdict is not acceptable.

`~/OpenBot/Shared/trendi-seo/monitor/latest.json`,
`monitor/history/<date>.json`, `monitor/state.json`, and the Hermes report at
`/opt/data/.workwatch/reports/hermes/seo-engine/<date>-seo-daily-monitor.md` (update
`latest.md`). A quiet day is `Status: quiet` and one line.

Never copy a key file into your profile home. The profile home has read-only symlinks
to the mounted `~/.config/trendi` and `~/.config/trendi-seo`; read through them.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/seo-engine/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/seo-engine/<YYYY-MM-DD>-seo-daily-monitor.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# seo-daily-monitor — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/seo-engine/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
