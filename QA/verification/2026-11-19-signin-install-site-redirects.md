# 2026-11-19 sign-in code, install copy, yearly line, /ai-receptionist redirects

- Sign-in code rule — cause: `tenant_invites.purpose` CHECK only allowed invite/recovery; prod was patched by hand. Fix: CREATE TABLE
  and an idempotent DROP/ADD at the end of schema.sql. Proof: `test_schema_accepts_a_code_row_and_is_idempotent`.
- False "we emailed a code" — cause: `owner_email_code` swallowed every failure and returned 200. Fix: 503 when a known account got no
  email; unknown addresses still 200; the Studio shows a fixed sentence. Proof: tests in `test_owner_code_signin.py`; mutation (removing
  the raise) fails two of them.
- Install page — Safari/Chrome/Firefox/Edge share hints, default-browser line, no "Safari only" claims. Proof: `test_pwa_install.py`.
- Yearly billing on request — visible line only on pricing.html and concierge.html; no yearly price, offer or link.
- Redirects — cause: website.mjs read `_redirects` once at start. Fix: mtime reload, restart of `website` after deploy-site.sh,
  slash/.html variants, MONEY_PAGES on /ai-office*, redirect check inside `site:pages`. Proof: `test_site_redirects.py`.
- Not done here: the built Studio bundle (`api/static`) is not rebuilt; deploy and restart are Jo's step.
