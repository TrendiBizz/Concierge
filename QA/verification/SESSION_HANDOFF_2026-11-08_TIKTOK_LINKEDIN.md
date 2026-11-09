# SESSION HANDOFF — TikTok complete in sandbox; LinkedIn customer OAuth next
Date: 2026-11-08 (Pacific/Auckland)
Owner: TrendiBizz / Trendi Concierge
Repository: https://github.com/TrendiBizz/Concierge
Branch: integration/concierge-v1
Remote computer: Mac.hub (Desktop Commander ID 94c529fd-3d2c-4396-a68d-cc86d0d2fb74)
Working tree: /Users/jo/work-staging/concierge-integration

## Mandatory product architecture
TrendiBizz.com is the established public business website. Trendi Concierge is TrendiBizz's **flagship integrated product**, NOT an independent public commercial brand. Secure application and OAuth callback stay on concierge.trendibizz.com. Keep the complete Concierge product in TrendiBizz/Concierge; Trendiisales/trendi-site is the existing website/design/SEO. Do not fragment the product or replace the live website.

## TikTok — what is now confirmed
- User created Sandbox **Trendi Concierge Test** within TikTok Developer app **Trendi Concierge**, selected Login Kit for Web, scope **user.info.basic**, configured exact HTTPS callback, and applied sandbox settings.
- Previous `unauthorized_client/client_key` disappeared after sandbox configuration applied. User supplied screenshots of the **real TikTok (Sandbox) consent** screen for Trendi account and the subsequent owner portal showing `tiktok — Trendi`.
- Independent Mac.hub verification: encrypted SQLite `.private/oauth-staging/social.db` contains **one account each for facebook, instagram, tiktok**. Private staging config `.private/oauth-staging/social.env` contains TikTok client key, secret and callback; mode 0600; values never printed. Authenticated Rust `/v1/oauth/providers` returns TikTok/Facebook/Instagram true, LinkedIn false.
- User recorded genuine Mac screen capture `/Users/jo/Desktop/Screen Recording 2026-11-08 at 15.01.46.mov` (142.66 s); it was cut (first 25 s) into `/Users/jo/Desktop/Trendi_Concierge_TikTok_25sec.mp4` (H264 1920x1080, duration 25.001s, 1,745,992 bytes) and a private QA copy at `QA/verification/tiktok-review/Trendi_Concierge_TikTok_25sec.mp4`. Original not modified. Video submitted/attached in TikTok Production app-review form as observed from user screenshot. **The final 'Submit' action and TikTok review status have NOT been independently confirmed**. Last screenshot showed a submission-reason modal, and assistant supplied reason text, but no post-submit confirmation. Do not claim approved or under review unless verified.
- Publishing remains DISABLED and separate from account linking. No live post verified or approved.
- Source: Rust `concierge-stack/social-service/src/tiktok.rs`, owner API `api/app/main.py`, bridge `api/app/social_bridge.py`, owner UI `api/static/owner.html`.
- TikTok activation verification note: `QA/verification/TIKTOK_SANDBOX_ACTIVATION_VERIFICATION_2026-11-08.md`; video checklist: `QA/verification/TIKTOK_SANDBOX_REVIEW_VIDEO_CHECKLIST.md`.
- Do not stage/commit video, private OAuth credentials, screenshots, or `QA/verification/office-shots/`.

## LinkedIn — user's NEXT priority; finish as much as permissions allow
Current Rust code: `concierge-stack/social-service/src/linkedin.rs`.
Current key constants:
- Authorization: `https://www.linkedin.com/oauth/v2/authorization`
- Token: `https://www.linkedin.com/oauth/v2/accessToken`
- OIDC profile: `https://api.linkedin.com/v2/userinfo`
- Scope CURRENTLY `openid profile w_member_social`; **important review point:** requesting posting scope for a login-only first-stage integration may require LinkedIn Share on LinkedIn Product entitlement and make customer onboarding harder. Inspect official current LinkedIn docs and separate essential member sign-in scopes from later approved posting. Do NOT enable publishing to circumvent approval.
- Env keys required: `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK` (all currently ABSENT in private staging env).
- Callback: `https://concierge.trendibizz.com/owner/social/oauth/callback`.
- Rust connector supports OAuth start, code exchange, `/v2/userinfo` identity verification, encrypted tokens, tenant-scoped account storage, unlink; tests exist.
- Owner UI already has Connect LinkedIn button `#social-linkedin-connect` but disabled until readiness true.
- Owner endpoints `POST /owner/social/oauth/linkedin/start`, `POST /owner/social/oauth/linkedin/finish`, `DELETE /owner/social/oauth/linkedin/accounts/{account_id}`.
- Existing setup `QA/verification/OAUTH_CONNECT_SETUP.md` says activate **Sign In with LinkedIn using OpenID Connect**, and **Share on LinkedIn** if `w_member_social` is required. For basic account linking, prefer minimum OIDC permissions and add posting separately only with user approval and platform permissions.
- LinkedIn Developer Portal https://www.linkedin.com/developers/apps — user previously saw **Create app**, with **no Products requested yet**. LinkedIn app setup requires association with business Page, client ID/secret, verified authorized redirect URI, and OIDC product approval; user may need to perform account-bound steps from their browser. Do not invent credentials or make claims that Product access is granted.
- If user has not created LinkedIn app, guide them through exact current UI (and perform Mac.hub changes independently where possible), minimizing effort. Never ask users to send secrets into chat. Set them in private staging config via hidden-terminal input, then restart only staging Rust launch agent and confirm readiness.
- Live verification: authenticated owner login, official LinkedIn consent, successful callback, one encrypted LinkedIn account row; test unlink/relink, wrong-tenant protections, and nonpublishing flags. Confirm before saying complete.
- Important product architecture: **one-click customer connection via TrendiBizz Concierge**; future customers should never create their own LinkedIn Developer app. TrendiBizz owns app credentials and customer grants consent through provider OAuth.

## Dependencies and services (preserve)
- Mac.hub authorized remote computer has `/Users/jo/work-staging/concierge-integration` on branch `integration/concierge-v1`.
- Rust OAuth staging: `com.trendi.concierge-oauth-social-staging` launch agent, health `127.0.0.1:4390/health`.
- Staging Docker API `concierge-oauth-staging-api` at localhost:8001; production API `concierge-api-1` at localhost:8000. Last verified all 200.
- Private `.private/oauth-staging/social.env` is 0600 and contains live sandbox/private provider material. Never display, copy to chat or commit. To query provider readiness without emitting the key, a local Python script can read `SOCIAL_CONCIERGE_KEY` from the env and request `http://127.0.0.1:4390/v1/oauth/providers`; print booleans only.
- Current Git HEAD before this handoff: `c4ddb94`. Untracked `QA/verification/office-shots/` belongs to unrelated work: preserve untouched. `QA/verification/tiktok-review/` contains untracked MP4: preserve, do not commit.
- Tests: Rust `(cd concierge-stack/social-service && CARGO_BUILD_JOBS=1 cargo test --locked -j 1 -q && cargo clippy --locked --all-targets -- -D warnings)`; Python `PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m unittest QA.verification.social_owner_integration_test -q`; browser `node QA/verification/owner_onboarding_browser.cjs`. Prefer focused tests first.
- Preserve LiveKit/Grok voice, Twenty CRM, backups, website, operating servers, tokens and data.
- No production deployment, merge, enabling publishing or live customer messaging, paid-provider changes without separate explicit authorization. Staging-only deployment is permitted after tests.
- On handoff resume: check actual repo/status/remote origin, current provider readiness, audit LinkedIn scope and official API requirements, improve implementation if warranted, run tests, commit/push only authorized work to same integration branch; deliver proven results and exact remaining developer portal action. Avoid repeated premature handoffs. User wants completion rather than endless questions, full code where requested, and regular progress updates.

## TikTok production review: confirmation still needed
The last user screenshot showed a modal asking 'Please describe your reason for this submission' with 120-character cap. Suggested explanation: 'Requesting Login Kit approval so TrendiBizz customers can securely connect TikTok accounts to Trendi Concierge.' No subsequent successful submission/approval screenshot was shown. Treat status as **submitted form prepared, review status unconfirmed**, not approved.
