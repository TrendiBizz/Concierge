# SEO / keyword plan — 2026-11-11

## Homepage changes shipped
- Title: **AI receptionist for small business | Concierge by Trendi**
- Meta: AI receptionist, website chat, phone, email, SMS, appointment booking,
  built-in CRM, USD $400/month, New Zealand and worldwide.
- New H2: **An AI receptionist for small businesses in New Zealand and worldwide**
  with copy covering virtual receptionist, answering service, after-hours,
  enquiry capture, CRM and internal links to the three existing AI-receptionist
  pages.

## Keyword clusters and page map
| Cluster | Target page |
|---|---|
| AI receptionist, AI receptionist NZ, best AI receptionist | `/ai-receptionist` |
| AI receptionist cost, how much does an AI receptionist cost | `/ai-receptionist-cost` |
| AI answering service vs human, virtual receptionist | `/ai-answering-service-vs-human` |
| AI receptionist New Zealand / Auckland | new NZ page (next) |
| after-hours answering, missed-call text back | new pages (next) |
| AI receptionist for builders / trades / real estate / clinics | industry pages (next) |
| AI chat widget for website, lead capture, appointment booking, CRM | `/concierge` |
| AI search visibility, generative engine optimization, get mentioned in ChatGPT | `/generative-engine-optimization`, `/get-mentioned-chatgpt-perplexity` |

## On-page checklist
- One H1 with the main phrase; keyword-rich H2 and first paragraph.
- FAQPage schema on each service page; Product/Service/Offer where relevant.
- Internal links between the clusters; descriptive anchors.
- NZ proof: Auckland, NZBN, local case notes, free consultation.
- Fresh dates and a visible last-updated line.

## Off-page
- Google Business Profile + Bing Places; consistent NAP.
- NZ directories, startup/AI directories, Crunchbase, Wikidata.
- Reviews, case studies, listicle outreach ("best AI receptionist NZ").
- Reddit/Quora answers with genuine help, not link drops.
- IndexNow on every change; Bing Webmaster + Search Console.

## Crawler policy caution
Blocking all AI crawlers also blocks the ones that cite you. For the public site,
allow search/citation bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot,
Googlebot/Bingbot) and consider blocking training-only bots (GPTBot, CCBot,
Bytespider). Keep the portal noindex and auth-gated.

## Cloudflare purge
- After a deploy that changes HTML: purge `/` (or all changed URLs).
- After changing `/site-i18n.js`, `.css` or `.json`: purge those exact URLs.
- Purge Everything is safe for this small site when many pages/headers change.


## Bot policy applied
- WAF rule `26bf0a72f35540548206c4b92d2099fc` blocks training/scraping AI bots;
  AI search/citation bots remain allowed.
- robots.txt mirrors the policy.
