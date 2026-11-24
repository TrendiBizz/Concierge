# Test customer accounts 1-3 (2026-11-25)

Ask (Jo): three customer accounts "Test 1/2/3" so outside users can test the onboarding hub.

- Added `scripts/vps/test_tenants.py` (admin API on the box): `create` (idempotent), `invite N [--email addr]`, `delete`.
- Synced with sync-tooling.sh (OK: repo and box agree). Ran `create` on the box: test-1, test-2, test-3 created; rerun printed "exists" x3.
- `invite 1` returned a link at https://concierge.trendibizz.com/studio#invite=... (not emailed, single-use, 24h).
- Tenants have no site_url, billing or real data. No mail/SMS/calls sent.
- Public URL: https://concierge.trendibizz.com/studio = 200. trendibizz.com/studio = 404 (Studio lives on the concierge host; configured onboarding_url).
- Hand out: run `invite N --email <tester email>` on the box when the tester is ready (links die after 24h).
- Remove: `python3 scripts/vps/test_tenants.py delete`.
