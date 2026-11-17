# Routine: Master daily brief

- Profile: `trendi-master`
- Schedule: `0 8 * * *` Pacific/Auckland
- Source: new master layer; the subagent reports are the input
- Status: active
- Approval: report only

## Procedure

A deterministic **LANE STATUS TABLE** is injected into this prompt by
`scripts/lane_status.py`. It is the only evidence of which lanes actually ran. Use it
verbatim: a lane listed as `NO REPORT`, `PAUSED` or `NO ROUTINE` has no fresh report,
whatever a `latest.md` file might say.

Create a missing `~/.workwatch/reports/hermes/<profile>/` directory only if you need to
read it; never write a report for another profile. A lane with no report is
`UNANSWERED (no report yet)`; it is not a question for Jo and not a reason to stop.

For each: note its `Status:` line and the date in the heading. A report older than 36
hours is stale: say `UNANSWERED (stale since <date>)` for that lane, do not treat it as
all clear.

Then:

1. Merge duplicate findings across lanes. The same CVE in the social draft and the
   news brief is one item.
2. Drop anything Jo already decided, anything that is only a restatement of
   yesterday's brief, and anything with no evidence.
3. Write the brief in the shape in your SOUL:
   `Status:`, `## What changed since yesterday` (max 3), `## Needs Jo` (numbered,
   yes/no or a concrete choice, with evidence and cost of being wrong), `## Blocked`
   (the exact missing thing), `## Today` (one or two moves).
   **Status rule:** `attention` if any lane is unanswered or stale; `quiet` only when
   every lane has a fresh report and none needs Jo; `blocked` only if this brief
   cannot be written. `## Today` is a next action for the work, never a description
   of this routine.
4. Save it to
   `~/.workwatch/reports/hermes/trendi-master/<YYYY-MM-DD>-master-daily-brief.md` and
   copy it to `latest.md`.
5. If every lane is quiet and there is no new decision, write
   `Status: quiet` and one sentence. Do not manufacture work.

## Do not

- Do not send or post anything, and do not run a deploy or a paid API call.
- **Never create or overwrite another profile's `latest.md` or any file outside
  `trendi-master/`.** If a lane has no report, write `UNANSWERED`. A placeholder
  "quiet" report is a fabrication and a policy violation.
- Do not overwrite a subagent's report.
- Do not ask Jo to initialise your own report directories. Create them; a missing
  subagent lane is `UNANSWERED (no report yet)`.
- Do not repeat an item that is already in `## Needs Jo` from the previous brief
  unless it is still unanswered; if it is, say `still open (n days)`.

## Finish

The brief is not done until it is on disk. Write it with the file tool to the exact
path above, then re-read it to confirm. If the write fails, say `WRITE FAILED` in the
response; do not claim it was written.
