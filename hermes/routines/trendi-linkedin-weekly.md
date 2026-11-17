# Routine: Trendi LinkedIn weekly draft

- Profile: `trendi-desk`
- Schedule: `0 9 * * 1` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/trendi-linkedin-weekly.md`
  (Grok Trendi Desk original in jo-brain `profiles-full/trendi-desk-to-openbot-workwatch.md` B)
- Status: active
- Approval: draft only; Jo pastes it

## Procedure

Draft **one** LinkedIn Company post for Trendi
(https://www.linkedin.com/company/trendi-nz/, trendibizz.com). The audience is
businesses worldwide, not NZ-only.

Read first:

- `~/jo-brain/trendi/offer.md`
- `~/jo-brain/trendi/honesty-and-deploy.md`
- the live site (the offer now includes Concierge; do not misstate it)

Rotate topics across: Indexed / Found / Mentioned, the live checker tools
(`/tools/robots-ai-check`, `/tools/site-check`), AI visibility for any company, brand
clarity (not Trendi Marketing Agency / Trendos), and honest how-to (the get-mentioned
page). Avoid repeating the last topic in
`/opt/data/.workwatch/reports/hermes/trendi-desk/linkedin/`.

Rules:

- No rank or mention promises. Mention is not the same as a link. Indexed, then Found,
  then Mentioned.
- A soft CTA to a real live URL. Check it returns 200 first.
- Plain English; Unslop the copy.
- Do not frame the offer as New Zealand-only.
- **Never use the word "free" anywhere in the draft.**
- No competitor names, no company-size or headcount language.

If there is nothing useful to say that week, still draft a short useful tip post.

## Output

Save the finished draft to
`/opt/data/.workwatch/reports/hermes/trendi-desk/linkedin/<YYYY-MM-DD>.md` and to the routine
report `<date>-trendi-linkedin-weekly.md` (update `latest.md`). The draft must be
ready to paste. Do not post or send anything on LinkedIn.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/trendi-desk/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/trendi-desk/<YYYY-MM-DD>-trendi-linkedin-weekly.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# trendi-linkedin-weekly — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/trendi-desk/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
