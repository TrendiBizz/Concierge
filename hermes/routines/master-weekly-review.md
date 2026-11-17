# Routine: Master weekly review

- Profile: `trendi-master`
- Schedule: `0 10 * * 1` Pacific/Auckland
- Source: new master layer; mirrors the Monday Workwatch review
- Status: active
- Approval: report only

## Procedure

1. Read every report under `~/.workwatch/reports/hermes/*/` from the last 7 days.
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
   `~/.workwatch/reports/hermes/trendi-master/weekly-<YYYY-MM-DD>.md` and update
   `latest.md`.

## Do not

- Do not change a rule, a schedule or a procedure from this routine. Propose it in
  the review; Jo or the next install changes it.
- Do not invent a shipment. If there is no deploy id or file change, it did not ship.
