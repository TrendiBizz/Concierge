# Routine: Innovation scout (Trendi)

- Profile: `seo-engine`
- Schedule: `0 10 8,22 * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/seo-innovation-scout.md`
- Status: active
- Approval: ideas only; never acts externally

## Procedure

Fortnightly scout for new ways to get Trendi noticed.

1. Read `~/jo-brain/AGENTS.md`, `~/OpenBot/Shared/trendi-seo/ideas.csv` (create if
   missing: `date, idea, category, source_url, effort 1-5, likely_impact 1-5, score,
   status, notes`) and the "Trendi coverage & promotion plan" in
   `~/jo-brain/bots/handover/trendi-desk.md` and `~/jo-brain/trendi/social.md`, so
   ideas are not repeated.
2. Look with free sources at:
   - search/AI answer engine changes (Google AI Overviews and AI Mode, Bing Copilot,
     ChatGPT search, Perplexity, Gemini);
   - new free directories or citation sources in global English markets;
   - new or underused schema types;
   - link-earning free-tool ideas;
   - competitor moves (describe the category, do not name brands in customer copy);
   - community/Q&A placements.
3. Every idea needs a real source URL. Never invent facts or promise rankings. Score
   effort vs impact, append to `ideas.csv`, and mark stale ones.
4. Never act externally: no sign-ups, posts, listings or emails.

## Report

The top 1–3 new ideas (why it matters, effort) asking yes/no on each. If nothing is
worthwhile, write `Status: quiet` and say nothing else.

Save to `/opt/data/.workwatch/reports/hermes/seo-engine/<date>-seo-innovation-scout.md` and
update `latest.md`.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/seo-engine/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/seo-engine/<YYYY-MM-DD>-seo-innovation-scout.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# seo-innovation-scout — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/seo-engine/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
