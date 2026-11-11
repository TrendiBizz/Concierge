# GEO / AI visibility plan — 2026-11-11

## What the site already has (audited live)
- robots.txt allows Googlebot, Bingbot, OAI-SearchBot, PerplexityBot,
  Claude-SearchBot, Google-Extended, Applebot, GPTBot.
- llms.txt with public pages, official profiles, pricing facts and Concierge access.
- sitemap.xml (29 URLs) + meta/canonical/OG on pages.
- JSON-LD: Organization (legal name, NZBN, sameAs socials), WebSite, Service +
  Offer + UnitPriceSpecification, FAQPage, Article, BreadcrumbList on the main
  pages; comparison pages (FirstIndex, Otterly, Profound), guides and tools.
- Static, fast pages served by Caddy/Cloudflare.

## What actually moves AI answers
1. **Being indexed** by Bing (ChatGPT/Search) and Google (AI Overviews/Gemini).
2. **Citations from sources the model trusts** — listicles ("best AI receptionist
   NZ"), directories, reviews, press, Reddit/Quora, partner pages.
3. **Entity consistency** — same name, NZBN, socials, contact everywhere.
4. **Answer-shaped content** — direct answers, comparisons, prices, limits,
   fresh dates, clear headings.
5. **Measurement** — you cannot improve what you do not check.

## Done now
- IndexNow key at `https://trendibizz.com/3a226d049abaa3f61aeeb0b3f9a6c6b9.txt`
  and all 29 sitemap URLs submitted (HTTP 202). Future deploys:
  `python3 scripts/seo/indexnow.py`.

## 30-day actions
### Technical / index
- Verify Bing Webmaster Tools and submit sitemap (IndexNow already pings it).
- Verify Google Search Console; submit sitemap; check coverage.
- Re-run IndexNow after every content change.

### Entity / off-site (owner actions, highest leverage)
- Google Business Profile (if eligible) + Bing Places, consistent NAP.
- Wikidata entry for TRENDI LIMITED (NZBN) with official URL and socials.
- LinkedIn company page complete; same description/URL.
- NZ directories and startup/AI directories; Crunchbase; partner pages.
- Reviews (Google/LinkedIn) and 2–3 genuine case notes with permission.
- Outreach to existing "best AI receptionist / AI answering service" listicles
  asking to be considered; never buy placements.
- Answer real questions on Reddit/Quora/industry forums, linking only where useful.

### Content for prompts
- Add/adjust pages for: "AI receptionist NZ", "AI answering service vs human",
  "how much does an AI receptionist cost NZ", "Concierge alternatives",
  "AI receptionist for small business NZ". Keep the no-guarantee language.
- Refresh dates and stats monthly; add one comparison page per quarter.

## Measurement (weekly, 15 minutes)
Track each prompt in ChatGPT, Perplexity and Gemini (and Bing/Google AI results):

| Prompt | Mentioned? | Cited URL | Position/context | Date |
|---|---|---|---|---|
| best AI receptionist NZ | | | | |
| AI receptionist cost NZ | | | | |
| AI answering service vs human | | | | |
| Trendi Concierge | | | | |
| AI receptionist for small business NZ | | | | |

Also watch Cloudflare analytics for referrers `chatgpt.com`, `perplexity.ai`,
`gemini.google.com`, `copilot.microsoft.com`.

## Honest limits
No ranking, citation or AI-mention is guaranteed. Models choose sources; the
work above maximises the chance of being retrieved and cited.
