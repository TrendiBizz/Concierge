# 2026-11-27 SEO audit fixes (claude-seo report ~/Reports/claude-seo-test/report.md)

Fixed
- Titles over 60 chars: 6 named in the report plus 3 more it did not crawl (penetration-testing-checklist 68, pricing 65, smith-ai-alternative 69). All now <= 60; og:title and JSON-LD names updated to match. scripts/seo/make_page.py updated so regenerating cannot restore the long titles.
- Homepage title suffix "| Concierge" -> "| Trendi" (matches every other page).
- /guide: retired HowTo schema removed, replaced with Article (same description/dates). Visible date, data-updated, dateModified bumped to 2026-11-27 and sitemap lastmod regenerated with `site_seo.py sitemap --write`.
- Thin pages /ai-phone-answering and /ai-answering-service: three new sections each (typical call, what you see afterwards, setup / control / comparison), main text now ~600 and ~680 words. Only facts already published on the site or shown in the product (alert email, Slack/Teams, takeover, global pause, calendars, transcripts, CRM). One unverifiable sentence (repeat-caller recognition) was removed before commit.
Gate/test
- site_seo.audit now fails on titles > 60 chars and on HowTo schema (TITLE_LIMIT, DEPRECATED_SCHEMA). Test: scripts/seo/test_site_seo_titles.py (3 tests). Mutation check done: limit raised to 6000 and HowTo ban emptied -> 2 of 3 tests fail; restored -> all pass.
- `site_seo.py check`: OK 54 pages.
Not done (needs Jo)
- /goodcall-alternative (578 words) and /allo-alternative (597) not expanded: a useful comparison needs verified competitor pricing/features and I will not invent them. Provide sources or approve a product-facts-only expansion.
- FAQPage schema left in place (report: Info only, no harm).
- Page speed (Core Web Vitals) and the 22 uncrawled URLs not measured here.
