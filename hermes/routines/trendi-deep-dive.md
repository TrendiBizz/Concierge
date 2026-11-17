# Routine: Trendi SEO forums daily deep dive

- Profile: `trendi-desk`
- Schedule: `30 7 * * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/HANDOVER.md` section 15b (Grok Workwatch
  07:30 routine)
- Status: active
- Approval: research and advice only

## Purpose

Taken over from Jo's deleted OpenBot "Trendi" agent: "Search all SEO forums/websites
and ensure we have the correct mechanisms and infrastructure to compete with other
SEO providers." Run the daily deep dive on the SEO industry and on Trendi's own
product.

## Procedure

1. Research current discussions and implementations across the major SEO platforms
   and forums with web search and fetch. Cover:
   - the official forums and blogs of the major SEO tools and vendors;
   - Reddit communities such as r/SEO, r/bigseo, r/TechSEO, r/localseo,
     r/GEO_optimization, r/sem, r/SEO_LLM, r/Agent_SEO, r/seogrowth and r/aeo;
   - WebmasterWorld, BlackHatWorld and GrowthBar;
   - recent vendor announcements.

   Prefer primary sources. Reddit only works through RSS; space requests about 8s
   apart. Focus on what is new since the previous report.
2. Read the last couple of reports under
   `~/.workwatch/reports/hermes/trendi-desk/deep-dive/` and the delta notes so you do
   not repeat them.
3. Check Trendi's own offering at https://trendibizz.com against the go/no-go build
   plan in `~/OpenBot/Shared/workwatch/ops/deep_dive/CUSTOMER_SEO_CHECKER.md` and the
   Trendi docs in `~/jo-brain` and `~/OpenBot/Shared/trendi-site`. Check whether the
   public Site snapshot checker is live, whether the Worker, PageSpeed and Search
   Console steps are done, and whether the honesty rules and MVP scope are respected.
   Use at most one call to the site check endpoint: it allows 5 per IP per hour.
4. Advise on any additions or changes needed to keep the implementation correct and
   in line with the research. Trendi targets English-speaking businesses worldwide,
   with NZ as one market.
5. Report concisely: the key shifts, remaining scepticism or gaps, implementation gaps
   or advice, and what it means for the Indexed / Found / Mentioned playbook. Open
   with 3 short lines: what you found, what Jo must approve, what is unsure.

## Output

Save the report to
`~/.workwatch/reports/hermes/trendi-desk/deep-dive/<YYYY-MM-DD>.md` with a delta note
under `.../deep-dive/research_notes/<YYYY-MM-DD>_delta.md`, and copy the report to
`<date>-trendi-deep-dive.md` (update `latest.md`). If nothing new turned up since the
last report, write `Status: quiet` and one line.

This is research and advice only. Do not change the site, deploy, post or message
anyone. Fixes go to Jo as recommendations.
