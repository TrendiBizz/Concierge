# Follow-ups 2026-11-23 (Jo): social posting core, one all-inclusive price, least-privilege Cloudflare tokens

## A. Social posting is a core Concierge function
- Cause: the 23 Nov audit pass relabelled it "Optional" and removed it from chips, jump nav and the FAQ.
- Fix: /concierge hero chip, jump nav link, "Social posting, included" section, "What is Concierge?" FAQ and JSON-LD (Service + FAQ), price card tick; included in /pricing ticks, /ai-office card and JSON-LD, llms.txt.
- Matches code: `api/app/routers/social.py` (compose, schedule, status, OAuth per network), `api/app/social/` (approval tokens, guardrails, publishers for Facebook, Instagram, LinkedIn, X, TikTok, Google Business). Publishing stays per network, after platform approval where required; the copy keeps that caveat.

## B. The USD $250 price includes everything in Concierge
- Wording on /pricing (tick list, note, FAQ, JSON-LD), /concierge (price card, note, FAQ, JSON-LD), /ai-office (FAQ, JSON-LD), /ai-office-nz, /ai-office-cost ("Does it include a phone number?" = yes, setup fee = none, "What is included"), /terms pricing section, llms.txt.
- SEO and AI visibility (USD $500) and penetration testing are stated as separate products, priced separately. No Stripe link or price changed.
- What stays true and is still said: the customer's own mobile plan (texts via the paired smartphone) and their own phone provider's landline forwarding are billed by those companies, not Trendi.

## C. Cloudflare tokens
- Cause: Keychain `trendi-cf-readonly-token` was an account-wide admin token (hundreds of write permissions incl. WAF, cache, purge, token create), read by the tamper watch and the deploy purge.
- Fix: two account-owned tokens created via the API using that token's token-create right: `trendi-cf-tamperwatch-readonly` (GET only) and `trendi-cf-deploy-cache-token` (Cache Purge, Cache Settings Write, Zone Read; zone trendibizz.com only). Scripts updated: `scripts/security/tamper/run-snapshot.sh`, `scripts/vps/deploy-site.sh`, tamper README, ROUTINES_PASTE_READY.md, `docs/AGENT_WORKING_ORDER.md`.
- Proof: watch token GETs 200 on zone, DNS, settings, rulesets, WAF, cache rules, SSL, Workers routes; refused (401/403) on purge and ruleset PUT. Deploy token: purge 200, WAF GET/PUT and DNS GET all 403.

## Tests
`api/tests/test_followups_20261123.py`; mutation check: removing the hero chip fails the social test.
