# Pricing consistency — 2026-11-25

Question (Jo): `pricing.html` says "from USD $199 a month" but other copy says $400; why is it not fixed?

## Finding (FACT, grep of the tree)
- There was no live mismatch. Concierge is USD $199/month (3-month minimum) in `website/products.js`, `pricing.html`, every page, `llms.txt`, schema Offer (199) and `api/app/a2ui.py`. SEO is USD $499. Retired price was $250 (changed to $199 in `073bd96`, 2026-11-24).
- The only "$400/month" was one line in `QA/verification/SEO_KEYWORDS_2026-11-11.md` (a homepage meta draft). It is not on the site. I repeated it in my 2026-11-25 competitor record as if it were live copy; that was my error from not checking the site first.
- Why it looked unfixed: nothing in the repo recorded the canonical price or failed when a retired one appeared, and the stale line sat in a QA file.

## Fix
- Correction note added to the top of `SEO_KEYWORDS_2026-11-11.md`; the competitor record's pricing caveat is withdrawn here.
- `api/tests/test_site_pricing_consistency.py`: fails if "$250"/"USD 400" style prices appear in site pages, `llms.txt`, `products.js`, `a2ui.py`, and checks the settings price matches the pages. Mutation check: set products.js price to 400 -> test failed; restored.
