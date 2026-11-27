# 2026-11-27 health check FAIL "site:seo: https://trendibizz.com/rss.xml has no canonical"

- Cause: PR #94 (merged today) added /rss.xml to the sitemap. check_site_seo requires every sitemap URL to carry a canonical and robots meta in its HTML head; an RSS feed is XML with no head, so it failed on every run. The site itself was fine (feed 200, 16 items).
- Fix: scripts/vps/healthcheck.py treats sitemap URLs ending .xml as feeds: they must be served (200) and contain <rss or <feed; canonical/robots meta are not required. An .xml entry that is not a feed still fails.
- Tests: api/tests/test_site_seo.py (feed passes; non-feed xml fails). Mutation check done: guard disabled -> feed test fails; restored -> passes.
