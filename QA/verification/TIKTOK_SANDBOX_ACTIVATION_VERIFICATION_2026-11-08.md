# TikTok Sandbox Activation — verified results (8 November 2026)

## Verified on Mac.hub

- Repo: `/Users/jo/work-staging/concierge-integration`; branch `integration/concierge-v1`.
- Private staging config `.private/oauth-staging/social.env` contains TikTok client key, client secret, callback. Mode `0600`. No values were printed or committed.
- Live Rust readiness query authenticated with its private service key returned `tiktok=true`, `facebook=true`, `instagram=true`, `linkedin=false`, `mastodon=false`, `google_business=false`.
- HTTPS owner portal returned HTTP 200; staging and production services were healthy.
- Real Rust TikTok `POST /v1/customers/trendi-oauth-staging/oauth/tiktok/start` returned 200. Only parsed properties were checked; the URL, client key and state were not logged.
- Generated authorization URL used exactly `www.tiktok.com/v2/auth/authorize/`, with matching configured client key, `response_type=code`, `scope=user.info.basic` **only**, registered callback `https://concierge.trendibizz.com/owner/social/oauth/callback`, and a matching randomly generated OAuth state.
- TikTok's authorization endpoint returned HTTP 302 to a login/authorization page. This is **not** proof of actual sandbox-user consent.
- Browser check loaded the real staging HTML against synthetic owner-response fixtures derived from the authenticated provider-readiness result. The TikTok Connect button was visible, enabled, labelled 'Connect TikTok', with zero JavaScript errors. The check did **not** use a real owner login or submit provider authorization.
- Current encrypted account store had one Facebook and one Instagram entry; TikTok had **no** connected account at the time of verification.
- No live publishing or customer posting was enabled.

## Not verified / requires authorized action

1. TikTok Developer Portal Sandbox > Settings > Target users: add an authorized TikTok test account by signing in and consenting. This cannot be performed from the current unattended terminal session.
2. Confirm Login Kit for Web in the Sandbox product configuration and exact callback URI above. Remove other unimplemented products/scopes from the initial review.
3. Sign into the real Concierge owner portal, click Connect TikTok and complete TikTok Login Kit using that target user.
4. Verify after callback that the account appears in the tenant-scoped encrypted account database with no reauthorization required; inspect consent and test disconnect/relink.
5. Record the **genuine** HTTPS owner portal + TikTok sandbox consent + connected-account UI. Do not fabricate or splice simulated consent.
6. Compress/validate the actual screen recording with `scripts/prepare-tiktok-review-video.zsh`, check that it contains no secrets and is under 50 MB.
7. In the authenticated Developer Portal, upload the recording and submit for review. TikTok's domain verification requirements should be followed as shown in that specific app's configuration; for Sandbox, TikTok docs currently say verification is required only for Content Posting API.

No TikTok app review was submitted, and no genuine demonstration MP4 exists yet. Do not claim otherwise.

## Separate LinkedIn dependency

LinkedIn OAuth code and UI exist, but the staging config does not contain a LinkedIn app/client secret or approved Products. The owner must create/request appropriate LinkedIn developer products and authorize the app before live verification can be performed.

## Official references

- https://developers.tiktok.com/docs/en/login-kit-web
- https://developers.tiktok.com/docs/en/add-a-sandbox
- https://developers.tiktok.com/docs/en/app-review-guidelines
- https://developers.tiktok.com/docs/en/getting-started-create-an-app
