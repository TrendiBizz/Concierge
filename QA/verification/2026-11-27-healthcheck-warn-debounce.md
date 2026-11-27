# Health-check mail for a single network blip (2026-11-27)
## Cause
Box log 2026-11-27 08:5x UTC: several public fetches from the box returned HTTP 0 (trendibizz.com in 15.6s, chat widget in 23.3s, /concierge). `check_site_prices` used the non-retrying `http`, so it returned WARN "could not read the pricing page (page 0, plans 200)", and `plan_notifications` mailed warnings on first sight (only fails waited for a second run). The next run was all-ok (53 ok), so nothing was actually wrong.
## Fix
- `check_site_prices` uses `http_stable` (retries 0/502/503/504) for all three fetches.
- `plan_notifications`: a warning now needs two consecutive runs before it is mailed, same as a fail; a pending warning that clears leaves no trace. Mailed warnings keep the flap suppression and 48h window.
## Proof
New tests: test_a_single_run_warning_is_never_mailed, test_the_pricing_check_retries_a_blipped_fetch; three older tests updated to the two-run rule. Mutation (warns mailed on first sight again) -> 4 failures. Full suite 1988 passed.
Not fixed: why the box saw HTTP 0 for ~2 minutes (UNKNOWN; Cloudflare/route blip). A real outage still mails after two runs (~5-10 min).
