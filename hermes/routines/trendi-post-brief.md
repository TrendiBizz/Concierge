# Routine: Twice-monthly post brief (Trendi)

- Profile: `trendi-desk`
- Schedule: `0 9 3,17 * *` Pacific/Auckland
- Source: Grok Trendi Desk automation `twice-monthly-post-brief-trendi`, created
  2026-11-15 (3rd and 17th at about 09:00); the verbatim Grok prompt was not in the
  local cache, so this procedure is reconstructed from the recorded creation note and
  the standing Trendi rules.
- Status: active
- Approval: brief only; the post ships through the gate after Jo's yes

## Procedure

Twice a month, pick **one** topic worth a full Trendi post and brief Trendi Desk to
write it. Do not publish.

1. Pick the topic from sourced terms and Search Console data:
   - `~/OpenBot/Shared/trendi-seo/terms.csv` (only terms with a source)
   - GSC queries/impressions by country (last 28 days)
   - `~/OpenBot/Shared/trendi-seo/ideas.csv` (highest scored, not already used)
   - the Trendi coverage plan in `~/jo-brain/bots/handover/trendi-desk.md`
   Prefer a query Trendi can answer truthfully and that supports the Concierge offer.
2. Write the brief under `/opt/data/.workwatch/reports/hermes/trendi-desk/briefs/`:
   - working title and slug;
   - the exact search intent and the questions the page must answer;
   - the outline (H2/H3), with the real facts and sources for each section;
   - internal links to live pages (check each returns 200);
   - metadata: title, description (≤160 chars), canonical;
   - schema notes: `author` is **Trendi team** (Organization), never a personal name;
   - the one CTA (Concierge) and the secondary SEO link.
3. Copy rules: **Concierge leads**, SEO and AI visibility is the secondary offer.
   No "free". No GST; prices are in USD. No competitor names. No company-size or
   headcount language. Worldwide framing.
4. Mark the brief `READY FOR JO` and say what needs his yes. Do not create the page,
   do not stage a deploy, do not send it to the site repo.

## Output

Save the brief to
`/opt/data/.workwatch/reports/hermes/trendi-desk/briefs/<YYYY-MM-DD>-post-brief.md` and copy
it to `<date>-trendi-post-brief.md` (update `latest.md`). The report's `## Needs Jo`
is a single yes/no on the topic and outline.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/trendi-desk/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/trendi-desk/<YYYY-MM-DD>-trendi-post-brief.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# trendi-post-brief — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/trendi-desk/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
