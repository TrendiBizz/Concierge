# Concierge OAuth activation — operator checklist (2026-11-08)

All backend product work stays in `TrendiBizz/Concierge`. The public `trendi-site` repository is not an integration backend.

## Registered redirect

The verified staging redirect is **`https://concierge.trendibizz.com/owner/social/oauth/callback`**, reachable over Cloudflare HTTPS.
The host must be the one that serves `/owner-ui`, including the same scheme and hostname. A customer must log into Concierge and click Connect, then grant access in the provider's own login screen. No customer supplies developer keys.

The Rust service retains encrypted tokens, and the owner API proxies owner-authorized operations without passing provider secrets to browsers. An OAuth configuration flag means **configured**, not externally certified.

## Developer apps Trendi must control

**Meta Facebook Pages — EXISTING APP: SocialSync, App ID `676274422041376`**
1. Reuse the existing **SocialSync** Meta Developer app (administrator access confirmed by the supplied 2026-11-08 screenshot). It is currently **in Development mode**, has **Type: None**, and shows **no selected business portfolio**. Do not create another app unless Meta proves its existing type/use cases cannot support the needed capabilities. The visible App ID is public and may be recorded in the tracked template; the **App Secret must never be committed**.
2. Open its dashboard and check that the **Facebook Login for Business/Pages** use case or product can be added. If the app's type prevents it, confirm that limitation in Meta before creating a replacement. Link the appropriate Trendi business portfolio where Meta requires it.
3. Register the exact OAuth redirect URI that serves the Concierge owner portal. Do not guess the public host name; verify HTTPS reachability first.
4. Configure app contact email, privacy policy URL, user-data deletion instructions, app domains, and allowed OAuth domains as required by the dashboard. Public privacy terms must accurately describe connected social accounts and tokens before approval.
5. For initial development tests, authorize an app role/tester who manages a real Facebook Page. Customer accounts outside app roles require Live mode plus App Review/Advanced Access as applicable.
6. Provide the App Secret only through Mac.hub's private `concierge-stack/social-service/data/social.env` or approved secret store. Its App ID is already preset in the tracked example and local private config.

For Facebook Pages grant `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`. The exact permissions required may vary with Meta's chosen Login product and its dashboard approval flow.

After approving the development permissions, test real Page enumeration, disconnect/reconnect, cross-tenant isolation and an explicitly approved text-only post. Do not enable production customer access while the app remains in Development mode.

**Meta Instagram — existing SocialSync Instagram Graph API with Facebook Login**
1. SocialSync already has **Instagram Graph API** installed. Use its Facebook Login product and the SAME Facebook App ID/secret; do not create a separate Instagram Login app for this configuration.
2. The default `SOCIAL_INSTAGRAM_LOGIN_MODE=facebook` uses `https://www.facebook.com/dialog/oauth`, Meta Graph API v27.0 and permissions `pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`.
3. The authorized person must manage a Facebook Page linked to an Instagram Business/Creator professional account. Concierge discovers only accounts returned by the trusted Page listing, encrypts the Page access token with a tenant/account-bound label, and posts images through versioned `graph.facebook.com` endpoints.
4. Test a professional account, a public HTTPS image URL, owner approval, connection/disconnection and receipt; Meta App Review/Advanced Access is required before onboarding unrelated customers.
5. The optional standalone **Instagram API with Instagram Login** path remains available only if a different Instagram Login product is expressly configured: set `SOCIAL_INSTAGRAM_LOGIN_MODE=instagram` and provide separate Instagram app credentials. It uses `instagram_business_basic`, `instagram_business_content_publish`, and `graph.instagram.com`. These two flows must not mix tokens, scopes, or refresh endpoints.
6. Linked Facebook Page tokens are not refreshed through the standalone `ig_refresh_token` endpoint. Revoke/expire requires secure reconnect; provider tests are still outstanding.

**Google Business Profile**
1. Set up a Trendi Google Cloud OAuth Web Application, exact HTTPS callback, and request scope `https://www.googleapis.com/auth/business.manage` with offline access.
2. Apply for and enable Google Business Profile API access for the project's OAuth client; verify eligible business locations controlled by authorized test owners.
3. Private variables: `SOCIAL_GOOGLE_CLIENT_ID`, `SOCIAL_GOOGLE_CLIENT_SECRET`, `SOCIAL_GOOGLE_CALLBACK`. The Rust adapter discovers authorized business accounts and locations, stores encrypted tokens per location, and supports token renewal.
4. Test a separately approved Standard local post via the Business Profile v4 API. This implementation currently supports text-only Standard updates; media, offers and events need separately verified adapters.

**LinkedIn**
1. In Trendi's LinkedIn Developer app, activate **Sign In with LinkedIn using OpenID Connect**. Basic customer connection requests only `openid profile`, without publishing access. Customer email is not requested.
2. Register exact callback `https://concierge.trendibizz.com/owner/social/oauth/callback` and supply client ID/secret only in the private staging environment. Customers never register their own developer apps.
3. Verify genuine LinkedIn consent, profile, encrypted account storage, tenant isolation, disconnect and relink. The configured flag alone is not evidence of working OAuth.
4. **Share on LinkedIn** / `w_member_social` is a separate later product grant and explicit reauthorization step for customers choosing publishing. Do not enable LinkedIn publishing for login-only accounts.
5. Programmatic refresh tokens require separate approved access where available; otherwise prompt for reconnection when the token expires.

**Mastodon**
1. Register app on the one configured HTTPS Mastodon instance with callback.
2. Grant `read:accounts write:statuses`; account authorizes itself.

**Other major networks**
TikTok, Bluesky OAuth, and X customer OAuth require additional official adapter development and provider-account approvals. Google Business Profile now has a local adapter but still requires live Google API approval and certification. They are NOT certified by the current Meta/LinkedIn/Mastodon service. Do not invent successful integrations or turn on placeholder buttons.

## Required private configuration

Set these only in the private service environment or the approved secret store (never in Git or chat):

- `SOCIAL_CONCIERGE_KEY`, `SOCIAL_AGENT_KEY` (separate 32+ character keys).
- `SOCIAL_VAULT_KEY` (32-byte random AES-GCM key in base64, backed up securely).
- `SOCIAL_DB` (persistent private SQLite path), `SOCIAL_BIND=127.0.0.1:4390`.
- `SOCIAL_FACEBOOK_CLIENT_ID`, `SOCIAL_FACEBOOK_CLIENT_SECRET`, `SOCIAL_FACEBOOK_CALLBACK`.
- `SOCIAL_INSTAGRAM_CLIENT_ID`, `SOCIAL_INSTAGRAM_CLIENT_SECRET`, `SOCIAL_INSTAGRAM_CALLBACK`.
- `SOCIAL_META_GRAPH_VERSION=v27.0` (latest confirmed from Meta release notes on 2026-11-08; re-audit on upgrades).
- `SOCIAL_INSTAGRAM_LOGIN_MODE=facebook` (the installed SocialSync Instagram Graph API product).
- `SOCIAL_GOOGLE_CLIENT_ID`, `SOCIAL_GOOGLE_CLIENT_SECRET`, `SOCIAL_GOOGLE_CALLBACK`.
- `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK`.
- `SOCIAL_MASTODON_ORIGIN`, `SOCIAL_MASTODON_CLIENT_ID`, `SOCIAL_MASTODON_CLIENT_SECRET`, `SOCIAL_MASTODON_CALLBACK`.

Concierge API also needs `SOCIAL_SERVICE_ENABLED=true`, `SOCIAL_CONCIERGE_KEY` identical to the Rust service key, and a verified private `SOCIAL_SERVICE_URL` route. Container/host routing must be verified separately.

Keep `SOCIAL_ENABLE_PUBLISH=false` and `SOCIAL_ENABLE_FACEBOOK_PUBLISH=false`, `SOCIAL_ENABLE_INSTAGRAM_PUBLISH=false`, `SOCIAL_ENABLE_GOOGLE_BUSINESS_PUBLISH=false`, `SOCIAL_ENABLE_LINKEDIN_PUBLISH=false`, `SOCIAL_ENABLE_MASTODON_PUBLISH=false` until separately authorized tests and production approval.

## Acceptance / independent evidence

- Developer application approved by provider; callbacks reach the actual HTTPS API.
- Two distinct customer accounts authorize through real provider login UI; each sees only its accounts.
- OAuth state is tenant-bound, expires and is single-use. Access/refresh tokens stay encrypted with account-bound labels.
- Facebook Page grants are verified, including content management. Instagram professional identity is verified.
- Owner can unlink/relink, and in-flight token renewal cannot defeat a disconnect.
- Customer drafts are owner-approved before the posting scheduler is enabled. Provider receipts must be recorded.
- An ambiguous API timeout is quarantined rather than retried as a duplicate post.
- Final operator approval is required before changing deployment or paying for provider services.

Existing local Rust/Python/browser test results validate code behavior **only**. They are not real provider authorization receipts.


## TikTok Login Kit (new Rust customer OAuth implementation, 2026-11-08)

- Register one Trendi TikTok for Developers app at https://developers.tiktok.com .
- Add Login Kit for Web and register exactly `https://concierge.trendibizz.com/owner/social/oauth/callback`.
- Add Content Posting API separately, requesting and obtaining approval for `video.publish` before any future posting integration. Publishing is NOT implemented or enabled by the Login Kit account connector alone.
- Set `SOCIAL_TIKTOK_CLIENT_KEY`, `SOCIAL_TIKTOK_CLIENT_SECRET`, and `SOCIAL_TIKTOK_CALLBACK` only in gitignored private social configuration. Do not put credentials in Concierge browser or Git.
- The customer uses the Concierge Connect TikTok button, authorizes only `user.info.basic` for account discovery, and the Rust service verifies `open_id` against the official TikTok User Info API.
- TikTok access and refresh tokens are encrypted per tenant/account, one-time OAuth state is enforced, and token rotation uses the official refresh endpoint. All social publishing remains disabled.
- Until TikTok application credentials and approved Login Kit permissions are available, the TikTok Connect button stays disabled and cannot be falsely certified as working.
