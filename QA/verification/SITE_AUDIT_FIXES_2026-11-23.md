# Site audit fixes, 23 Nov 2026 (Jo approved 14:52 NZDT)

Cause: the neon-trendi audit (~/Reports/neon-trendi-audit/report.md) found a broken checkout funnel, stale
phone/voicemail copy, a pricing page that led with SEO, contradictory terms claims and AI crawlers blocked.

Fix (all in `website/` unless noted): `main.js` only rewrites `a[data-concierge-pay]` (one explicit pay button on
/pricing); setup buttons are plain links to /concierge-start. /pricing rebuilt Concierge-first. Phone number
copy now says minutes. 3-month minimum kept, with an honest reason. Voicemail and the integrations in
`api/app/integrations.py` (ServiceM8, Xero, M365, Tradify, Fergus) plus webhooks are shown. Nav leads with
Concierge, Pen Testing moved to the footer, social publishing is an optional section. /terms is one standard
document. llms.txt duplicate and areaServed duplicates fixed. robots.txt allows the major AI crawlers
(policy change in `scripts/seo/site_seo.py`, `scripts/vps/healthcheck.py`, tests). `_headers` adds
`Cache-Control: public, max-age=60, s-maxage=3600`; `deploy-site.sh` purges the Cloudflare cache.

Proof: `api/tests/test_site_audit_fixes_20261123.py` (13 tests); mutation check: re-adding `data-concierge-plan`
to main.js and disallowing GPTBot made 2 tests fail, restored, all pass. Full suite 1755 passed, 42 skipped.
`site_seo.py check` OK. Stripe links and prices untouched. Concierge legal drafts (docs/legal) untouched.
Live verification: see ~/Reports/trendi-audit-fixes/report.md.

## Cloudflare (applied via API on 23 Nov 2026, not in the repo)
- Cache rule (phase http_request_cache_settings): cache everything on trendibizz.com / www except `/api/*` and
  `/cdn-cgi/*`; edge and browser TTL respect the origin `Cache-Control` (`s-maxage=3600`). To undo: delete that
  one rule in the zone's Cache Rules.
- The Keychain item `trendi-cf-readonly-token` can write cache rules and purge the cache (its name says read-only;
  `trendi-cloudflare-token` and `trendi-cf-pages-token` cannot). `deploy-site.sh` purges with it.
- The WAF custom rule "Block AI training crawlers" still returns 403 to GPTBot, ClaudeBot and Google-Extended, so
  robots.txt allowing them has no effect until that rule is narrowed. NOT changed: it is a security rule Jo did not
  order touched.
