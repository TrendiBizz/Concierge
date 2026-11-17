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
2. Write the brief under `~/.workwatch/reports/hermes/trendi-desk/briefs/`:
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
`~/.workwatch/reports/hermes/trendi-desk/briefs/<YYYY-MM-DD>-post-brief.md` and copy
it to `<date>-trendi-post-brief.md` (update `latest.md`). The report's `## Needs Jo`
is a single yes/no on the topic and outline.
