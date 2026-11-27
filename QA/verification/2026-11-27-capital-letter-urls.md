# 2026-11-27 /Concierge (capital C) returned 404

- Cause: the website server (scripts/vps/website.mjs) matches page paths case-sensitively; pages are lowercase only, so a typed or bookmarked /Concierge hit the 404 page. Site was not down (/, /concierge, /pricing all 200).
- Fix: CASE-301 rule in website.mjs. A path containing capitals, with no file of that exact spelling and with the lowercase spelling resolving to a page, now 301s to the lowercase URL (query string kept). Unknown pages still 404; real files with capitals (e.g. images) are still served. One URL per page, so no duplicate-content risk.
- Trailing slash handled too (/Concierge/ -> /concierge). A deploy after the first fix showed Cloudflare had cached the old 404 for 1 h; deploy-site.sh purge cleared it.
- Exact-case check uses the directory listing, not realpath, so it holds on a case-insensitive filesystem (found by the test on macOS).
- Test: api/tests/test_website_case_redirect.py starts the real website.mjs against a temp site and requests /Concierge, /CONCIERGE?x=1, /concierge, /Nopage, /Logo.png. Mutation check done: rule disabled -> capital-path test fails; restored -> passes. Full suite 1933 passed.
- Deploy: website.mjs is host tooling and loads once at start: sync-tooling.sh, then restart-website.sh.
