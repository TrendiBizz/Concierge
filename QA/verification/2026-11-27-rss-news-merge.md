# 2026-11-27 RSS feed and /news index (PR #94) merged

- Merged origin/site/rss-and-news-index locally (no conflicts) and deployed through scripts/vps/deploy-site.sh.
- PR CI had 2 failures, both real: (1) tools/a2ui/pages.json lacked news/index.html, so test_every_html_page_has_exactly_one_widget failed; fixed by adding the entry. (2) SEO check "date in the future" because the PR carried 2026-11-27 dates and CI ran on 2026-11-26; passes now that the date is today.
- The feed carried two pre-rebuild titles (penetration-testing-checklist, how-does-an-ai-office-work); updated in rss.xml and news/index.html to match the shortened page titles from 200eaff. All 16 other feed titles already matched their pages.
- Proof: site_seo.py check OK 55 pages; full suite 1931 passed; feed is well-formed XML with 16 items.
