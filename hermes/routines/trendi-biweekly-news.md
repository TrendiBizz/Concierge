# Routine: Trendi biweekly SEO + pen-test news

- Profile: `trendi-desk`
- Schedule: `0 9 1,15 * *` Pacific/Auckland
- Source: `~/OpenBot/Shared/workwatch/routines/trendi-biweekly-news.md`
- Status: active
- Approval: drafts only; never posts

## Procedure

Draft a bi-weekly Trendi news update for Jo: SEO/AI-visibility snippets **plus**
penetration-testing / appsec developments. Draft only. Never auto-post to LinkedIn,
Instagram, Facebook, email or anywhere else.

Each run:

1. Pull fresh, public sources from roughly the last 2 weeks: Google Search Central and
   Bing Webmaster blogs, reputable SEO industry news, OWASP, CISA advisories, major
   browser/security vendor research blogs, and public Cloudflare/security research.
   Prefer primary sources over roundups. Verify each item with 2+ sources where
   possible.
2. Produce 4–6 short snippets total, mixing both lanes (at least 2 SEO/AI-search and
   at least 2 pen-test/appsec). Each snippet: one punchy line + 1–2 sentences of why
   it matters for Trendi clients or dogfooding trendibizz.com + a source link.
3. Honesty rules: no rank or mention promises; no invented metrics; report mentions
   vs links separately if AI search comes up; soften `llms.txt` (crawl readiness
   only); never invent numbers.
4. **Never name competitors** (no Ahrefs, Semrush, SE Ranking, BrightEdge, Surfer,
   other SEO agencies, other pen-test shops or rival brands). Describe the
   development in category terms.
5. No company-size / headcount / team-size language.
6. Worldwide framing (any business); TRENDI LIMITED is the NZ company of record only,
   so do not NZ-only the service area.
7. End with 2 ready-to-paste social drafts Jo can approve:
   - (A) one LinkedIn post under ~1,200 characters combining the best 2–3 points;
   - (B) one short Instagram caption under 150 words pointing at trendibizz.com where
     relevant.
   Both: no competitor names, no guarantees, and **never the word "free"**.
8. If there is genuinely nothing new worth posting, say so in one sentence and skip
   the social drafts.

## Output

Save to `/opt/data/.workwatch/reports/hermes/trendi-desk/news/<YYYY-MM-DD>.md` and to the
routine report `<date>-trendi-biweekly-news.md` (update `latest.md`). Do not send or
publish anything.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/trendi-desk/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/trendi-desk/<YYYY-MM-DD>-trendi-biweekly-news.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# trendi-biweekly-news — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/trendi-desk/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
