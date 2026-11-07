# SocialSync Facebook/Instagram OAuth completion — 2026-11-08

## Verified observed result
After the user initiated live Meta Facebook and Instagram authorization via the staging owner UI:
- Both OAuth `start` routes returned HTTP 200.
- Meta redirected to Concierge's public OAuth callback, which returned HTTP 200.
- Both OAuth `finish` POSTs returned HTTP 409.
- Private Rust staging SQLite contained **0 connected accounts**, **0 recorded consents**, and **0 pending OAuth states** when checked; pending states were consumed by the finish flow.
- All three staging/local/prod health endpoints returned HTTP 200.
- There is **no verified successful token exchange, Page discovery, Instagram account link or customer authorization**.

## Root cause of misleading displayed error
The Python social bridge mapped every Rust HTTP 400 or 409 into the generic `Social post cannot be changed in its current state`, including OAuth failures. This error was **not evidence** that any customer post existed.

## Fix deployed to staging
- Rust maps a limited allowlist of static, known Meta errors (permission denial, missing managed Pages, missing linked Instagram professional account, OAuth state expiry and provider rejection) to non-sensitive text. No third-party response JSON, OAuth codes or provider tokens are returned.
- Python maps known Meta OAuth failures to the correct HTTP 400 with a safe explanation, and preserves other errors as generic responses. Existing business onboarding race protection remains.
- Staging API and Rust process restarted **only** after local verification. No production API restart occurred.
- Tests: 45 Rust, 52 Python API, 14 owner/social tests passed.
- Independent health checks after staging restart: Rust 200, staging API 200, production API 200.
- Publishing remains disabled.

## Next action needed
A real account owner must re-run **Connect Facebook Pages** in the signed-in portal, then report the exact **new** error text, if any. The previously consumed authorization codes are intentionally not reusable. Use the returned category to identify whether SocialSync needs approved Page scopes, a managed Page, app roles/advanced access, or a corrected Meta exchange configuration. Repeat Instagram only after Facebook Page discovery is confirmed.

Do not claim OAuth is complete until an account appears in the encrypted store with verified identity and tenant ownership. Preserve `QA/verification/office-shots/` and all other untracked unrelated files.
