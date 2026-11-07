# Concierge OAuth activation — operator checklist (2026-11-08)

All backend product work stays in `TrendiBizz/Concierge`. The public `trendi-site` repository is not an integration backend.

## Registered redirect

Use **exactly** `https://<concierge-api-public-host>/owner/social/oauth/callback`.
The host must be the one that serves `/owner-ui`, including the same scheme and hostname. A customer must log into Concierge and click Connect, then grant access in the provider's own login screen. No customer supplies developer keys.

The Rust service retains encrypted tokens, and the owner API proxies owner-authorized operations without passing provider secrets to browsers. An OAuth configuration flag means **configured**, not externally certified.

## Developer apps Trendi must control

**Meta Facebook Pages**
1. Create or open a Trendi Meta Developer app (Facebook Login for Business / Pages).
2. Provide its Facebook client ID and secret to the approved private secret store.
3. Register the exact HTTPS callback.
4. Request `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`; complete Meta verification and app review where required.
5. Authorize a test user who manages an actual Facebook Page with content-management tasks.
6. Test list of Pages, linking, disconnection, and a separately approved text-only test post.

**Meta Instagram**
1. Configure *Instagram API with Instagram Login* in the Meta developer console (may have a distinct Instagram client ID/secret).
2. Register the exact HTTPS callback; request `instagram_business_basic` and `instagram_business_content_publish`.
3. Authorize an Instagram Professional account (Business/Creator), not a personal account.
4. Verify profile identity, token exchange to long-lived token, refresh, disconnect, and one separately approved image post from a **public HTTPS image URL**.
5. Confirm Meta App Review and business verification/advanced access needed for customer accounts outside app roles.

**LinkedIn**
1. In Trendi's LinkedIn app, activate Sign In with LinkedIn using OpenID Connect and Share on LinkedIn; authorize scopes `openid profile w_member_social`.
2. Register exact callback and provide private client ID/secret.
3. Verify profile, disconnect/relink and an approved test post.
4. Programmatic refresh tokens require approved Marketing Developer Platform access; otherwise the user must reconnect at token expiry.

**Mastodon**
1. Register app on the one configured HTTPS Mastodon instance with callback.
2. Grant `read:accounts write:statuses`; account authorizes itself.

**Other major networks**
Google Business Profile, TikTok, Bluesky OAuth, and X customer OAuth require additional official adapter development and provider-account approvals. They are NOT certified by the current Meta/LinkedIn/Mastodon service. Do not invent successful integrations or turn on placeholder buttons.

## Required private configuration

Set these only in the private service environment or the approved secret store (never in Git or chat):

- `SOCIAL_CONCIERGE_KEY`, `SOCIAL_AGENT_KEY` (separate 32+ character keys).
- `SOCIAL_VAULT_KEY` (32-byte random AES-GCM key in base64, backed up securely).
- `SOCIAL_DB` (persistent private SQLite path), `SOCIAL_BIND=127.0.0.1:4390`.
- `SOCIAL_FACEBOOK_CLIENT_ID`, `SOCIAL_FACEBOOK_CLIENT_SECRET`, `SOCIAL_FACEBOOK_CALLBACK`.
- `SOCIAL_INSTAGRAM_CLIENT_ID`, `SOCIAL_INSTAGRAM_CLIENT_SECRET`, `SOCIAL_INSTAGRAM_CALLBACK`.
- `SOCIAL_META_GRAPH_VERSION` (review and pin a supported API version).
- `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK`.
- `SOCIAL_MASTODON_ORIGIN`, `SOCIAL_MASTODON_CLIENT_ID`, `SOCIAL_MASTODON_CLIENT_SECRET`, `SOCIAL_MASTODON_CALLBACK`.

Concierge API also needs `SOCIAL_SERVICE_ENABLED=true`, `SOCIAL_CONCIERGE_KEY` identical to the Rust service key, and a verified private `SOCIAL_SERVICE_URL` route. Container/host routing must be verified separately.

Keep `SOCIAL_ENABLE_PUBLISH=false` and `SOCIAL_ENABLE_FACEBOOK_PUBLISH=false`, `SOCIAL_ENABLE_INSTAGRAM_PUBLISH=false`, `SOCIAL_ENABLE_LINKEDIN_PUBLISH=false`, `SOCIAL_ENABLE_MASTODON_PUBLISH=false` until separately authorized tests and production approval.

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
