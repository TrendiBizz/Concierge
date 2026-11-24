# Website Copy, Penetration Testing Restore & SEO $499 Pricing — 2026-11-24

## Cause
1. **Line-rental / "set up in minutes" Concierge minimum-term wording:** Commit `36395bc` (23 Nov 2026) introduced copy on `/pricing`, `/concierge`, `/ai-office`, `/ai-office-cost`, `/ai-office-nz`, `/concierge-start`, `/how-does-an-ai-office-work`, `/terms`, and `/llms.txt` explaining the 3-month minimum in terms of "Trendi also rents the phone number on your behalf, which is a real ongoing cost", "number rental", "rented business phone number", and "set up for you in minutes". This undervalued the offering by framing the minimum around telecom line rental instead of the hands-on setup, configuration, testing, and implementation work delivered for every customer.
2. **Penetration Testing removed from main nav and homepage:** Commit `36395bc` (PR #87, 23 Nov 2026) removed `<a href="/penetration-testing">Pen Testing</a>` from `<nav aria-label="Main">` across 40 pages (leaving 5 subdirectory pages with an older nav) and removed the `#svc-pen` service panel from `website/index.html`, locking the removal in `api/tests/test_site_audit_fixes_20261123.py`. Jo never requested removing Penetration Testing.
3. **SEO & AI Visibility pricing update:** Jo updated the done-for-you SEO & AI Visibility monthly plan price from USD `$500` to USD `$499` per month.

## Fix
1. **Rewrote minimum-term and setup copy across the site:**
   - Rewrote `#why-minimum`, Key points, Concierge card copy/ticks, and FAQs on `website/pricing.html` to explain the full hands-on setup, configuration, end-to-end channel testing, CRM/integration wiring, and rollout refinement included with no separate setup fee.
   - Removed all occurrences of `"rents the phone number"`, `"rented business phone number"`, `"rented phone number"`, `"number rental"`, `"real ongoing cost"`, and `"set up for you in minutes"` across `website/pricing.html`, `website/concierge.html`, `website/ai-office.html`, `website/ai-office-cost.html`, `website/ai-office-nz.html`, `website/concierge-start.html`, `website/how-does-an-ai-office-work.html`, `website/terms.html`, and `website/llms.txt`.
2. **Restored Penetration Testing across the site:**
   - Restored `<a href="/penetration-testing">Pen Testing</a>` to `<nav aria-label="Main">` uniformly across all 45 nav-bearing HTML pages (keeping `Concierge` leading with `class="nav-primary"`).
   - Restored the full `#svc-pen` service panel on `website/index.html` and added a Penetration Testing callout link under `#section-1` on `website/pricing.html`.
3. **Updated SEO & AI Visibility plan from USD `$500` to USD `$499` everywhere:**
   - Updated `website/products.js` (`monthly` and `deposit` plans set to `499`), `website/pricing.html`, `website/seo.html`, `website/index.html`, `website/terms.html`, `website/partners.html` (10% referral reward updated accurately to `USD $49.90`), `website/llms.txt`, `website/site-i18n.json` (26 locales), and all 17 remaining HTML pages citing SEO pricing.
   - Updated `scripts/build_chatgpt_product_feed.py` (`499.00 USD`, `USD $499 / month`, cache-busted image query `?v=20261124b`) and regenerated `website/chatgpt-products.csv` and `website/brand/products/trendi-seo-ai-visibility-monthly.png`.
   - Synced `dateModified` / visible `Last updated` to `2026-11-24` on updated pages and regenerated `website/sitemap.xml` via `python3 scripts/seo/site_seo.py sitemap --write`.
4. **Updated regression tests (`api/tests/test_site_audit_fixes_20261123.py`):**
   - Guarded against re-introducing rental / `"set up for you in minutes"` copy (`test_no_stale_phone_number_or_voicemail_copy`, `test_three_month_minimum_is_kept_with_implementation_reason`).
   - Enforced Pen Testing presence in `<nav aria-label="Main">` across all pages and `#svc-pen` on `index.html` (`test_pen_testing_is_in_the_top_nav_and_concierge_is_first`).
   - Enforced `$499` SEO pricing across all HTML, `llms.txt`, `products.js`, and `chatgpt-products.csv` (`test_seo_plan_price_is_499_everywhere`).

## Proof
- **Mutation check:** Temporarily mutated `website/pricing.html` (re-injected `"rents the phone number"`, removed Pen Testing from nav, reverted `USD $499` to `USD $500`). All 4 guards failed as expected (`exit 1`); restored file cleanly and all 67 site audit + SEO tests passed.
- **SEO contract:** `python3 scripts/seo/site_seo.py check` → `OK: 46 pages — canonical, robots, h1, snippet, dates, links, sitemap and IndexNow key all agree`.
- **Product feed check:** `python3 scripts/build_chatgpt_product_feed.py --check` → `OK: 3 rows valid in website/chatgpt-products.csv`.
- **Zero-residual grep:** Confirmed 0 remaining rental/`in minutes` matches and 0 remaining `$500` SEO price strings across `website/`.
- **Full API test suite, deploy, `scripts/seo-gate.sh`, and `scripts/vps/verify-deploy.sh`:** Verified before and after push/deploy.
- **External Stripe note:** SEO Stripe Payment Links (`00wcN70IP4hJdwU8FpcEw06` / `7sY7sNgHN6pR50obRBcEw05`) belong to a separate Stripe account outside VPS `api.env`; Jo notified to update those Payment Links to `$499` in Stripe Dashboard if still priced at `$500`.
