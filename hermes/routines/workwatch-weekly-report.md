# Routine: Workwatch weekly report

- Profile: `workwatch`
- Schedule: `0 8 * * 1` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/README.md` (Workwatch v2; the Grok Workwatch
  Mon 08:00 weekly report)
- Status: **paused** — reading `~/.workwatch/notes` exposes shell/git activity; needs
  Jo's explicit yes
- Approval: report only; never builds anything

## Prerequisite

Jo says yes to Hermes reading `~/.workwatch/notes`. Until then, do not read them.

## Procedure

1. Read the last 8 days of notes (`~/.workwatch/notes/YYYY-MM-DD.jsonl`) and report
   on 7 days — the same window as the Workwatch app. Use the summaries and counts,
   never raw shell history.
2. Apply Workwatch's four questions: are the inputs clear, the outputs predictable,
   the rules simple, and the frequency sufficient?
   - **Pile 1** — Hermes just does it.
   - **Pile 2** — Hermes drafts, Jo approves.
   - **Pile 3** — stays with Jo.
3. For each candidate: what it is, the evidence (count and dates), hours per year
   saved (state the assumption), and the pile. Recommend at most three.
4. Do not build anything from this routine.

## Output

Write to `~/.workwatch/reports/hermes/workwatch/<date>-workwatch-weekly-report.md` and
update `latest.md`. Lead with `Status:`. No personal detail, no message contents, no
raw shell lines.
