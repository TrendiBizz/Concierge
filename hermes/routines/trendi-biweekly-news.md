# Routine: Trendi biweekly SEO + pen-test news

- Profile: `trendi-desk`
- Schedule: `30 10 1,15 * *` Pacific/Auckland
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

Save to `~/.workwatch/reports/hermes/trendi-desk/news/<YYYY-MM-DD>.md` and to the
routine report `<date>-trendi-biweekly-news.md` (update `latest.md`). Do not send or
publish anything.
