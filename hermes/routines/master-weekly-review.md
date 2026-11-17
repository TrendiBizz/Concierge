# Routine: Master weekly review

- Profile: `trendi-master`
- Schedule: `0 10 * * 1` Pacific/Auckland
- Source: new master layer; mirrors the Monday Workwatch review
- Status: active
- Approval: report only

## Procedure

1. Read every report under `/opt/data/.workwatch/reports/hermes/*/` from the last 7 days.
2. Read the Trendi handovers in `~/jo-brain/bots/handover/` (especially
   `trendi-desk.md` and `seo-engine.md`) and the roster's open to-do list.
3. Produce a review with:
   - **Shipped / measured** — what actually changed this week, with evidence.
   - **Stale** — work that was reported as "next" for more than two weeks.
   - **Subagent health** — which lanes ran, which were quiet, which failed. A lane
     that failed twice is an incident, not a quiet week.
   - **One process change** — exactly one, with the reason and how to undo it.
   - **Next week** — the three things that matter, in order.
4. Save to
   `/opt/data/.workwatch/reports/hermes/trendi-master/<YYYY-MM-DD>-master-weekly-review.md` and update
   `latest.md`.

## Do not

- Do not change a rule, a schedule or a procedure from this routine. Propose it in
  the review; Jo or the next install changes it.
- Do not invent a shipment. If there is no deploy id or file change, it did not ship.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/trendi-master/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/trendi-master/<YYYY-MM-DD>-master-weekly-review.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# master-weekly-review — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/trendi-master/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
