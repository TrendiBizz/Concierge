# Routine: Workwatch weekly report

- Profile: `workwatch`
- Schedule: `0 8 * * 1` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/README.md` (Workwatch v2; the Grok Workwatch
  Mon 08:00 weekly report)
- Status: **active** since 2026-11-17 (Jo asked for Workwatch to be part of the Hermes
  setup and UI)
- Approval: report only; never builds anything

## Procedure

1. Read the last 8 days of notes (`~/.workwatch/notes/YYYY-MM-DD.jsonl`) and report
  on 7 days — the same window as the Workwatch app. Use the summaries and counts,
  never raw shell history, credentials or message contents.
2. Apply Workwatch's four questions: are the inputs clear, the outputs predictable,
   the rules simple, and the frequency sufficient?
   - **Pile 1** — Hermes just does it.
   - **Pile 2** — Hermes drafts, Jo approves.
   - **Pile 3** — stays with Jo.
3. For each candidate: what it is, the evidence (count and dates), hours per year
   saved (state the assumption), and the pile. Recommend at most three.
4. Do not build anything from this routine.
5. If the notes are missing or unreadable, write `Status: blocked` and the missing path.

## Output

Write to `/opt/data/.workwatch/reports/hermes/workwatch/<date>-workwatch-weekly-report.md` and
update `latest.md`. Lead with `Status:`. No personal detail, no message contents, no
raw shell lines.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/workwatch/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/workwatch/<YYYY-MM-DD>-workwatch-weekly-report.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# workwatch-weekly-report — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/workwatch/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
