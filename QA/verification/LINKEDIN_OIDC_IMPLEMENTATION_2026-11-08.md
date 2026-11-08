# LinkedIn account-linking implementation verification — 2026-11-08

Repo: `TrendiBizz/Concierge`, branch `integration/concierge-v1`.

## Implemented

- Customer LinkedIn account linking requests only `openid profile` (minimal OpenID Connect scope), without `w_member_social`.
- OAuth state remains tenant-scoped, expires after 600 seconds and can be consumed only once. Token exchange and LinkedIn `/v2/userinfo` identity lookup remain server-side; encrypted tokens and account-bound labels are preserved.
- LinkedIn token renewal no longer requires publishing entitlement for login-only accounts.
- The publication scheduler now checks `account_consents.granted_scopes` for `w_member_social` against the current tenant and connected account, and rejects LinkedIn publication without the explicit grant even if the publisher is later enabled.
- Customer-facing Connect LinkedIn remains readiness-gated; other provider connections, voice and production configurations were not modified.

## Verification

- `cargo clippy --locked --all-targets -- -D warnings`: passed.
- `cargo test --locked -j 1 -q`: passed (all Rust test binaries).
- `PYTHONPATH=QA/verification/shims:api .../venv-concierge/bin/python -m unittest QA.verification.social_owner_integration_test -q`: 14 passed.
- `node QA/verification/owner_onboarding_browser.cjs`: all reported owner/viewer checks passed.
- Rust staging health: HTTP 200.
- LinkedIn staging client ID, client secret and callback: not populated. No real LinkedIn OAuth consent, callback, storage or disconnect/reconnect was executed.
- `office-shots` and private TikTok review video were not staged, copied or altered.

## Required operator action before real provider certification

1. In https://www.linkedin.com/developers/apps, create or select the **Trendi Concierge** LinkedIn app, associated with the appropriate company LinkedIn Page.
2. On Products, request/activate **Sign In with LinkedIn using OpenID Connect**. **Share on LinkedIn is not required to link accounts.**
3. On Auth, register the exact authorized redirect `https://concierge.trendibizz.com/owner/social/oauth/callback`.
4. Insert app client ID and secret privately into `.private/oauth-staging/social.env` using Mac.hub local trusted tooling, and set `SOCIAL_LINKEDIN_CALLBACK` to that redirect. Do not paste any secret into chat or commit it.
5. Restart only the Rust OAuth staging launch agent, confirm the authenticated provider-readiness flag, sign in to staging Concierge, press Connect LinkedIn, approve LinkedIn consent, then independently verify the encrypted account, tenant isolation and disconnect/reconnect. Production deployment and social publication remain disabled.

Official references:
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin
