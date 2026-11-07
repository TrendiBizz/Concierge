# SocialSync OAuth smoke verification — 8 November 2026

Verified on Mac.hub against the isolated staging deployment `concierge.trendibizz.com`.

## Results
- Private SocialSync App Secret is stored (not printed), app ID matches `676274422041376`.
- OAuth staging API -> native Rust service works; `facebook=true` and `instagram=true` in provider readiness.
- Created a synthetic Rust-only OAuth smoke-test tenant using a random identifier, then invoked each provider's `start` route.
- Both provider routes returned a correctly formed `www.facebook.com/dialog/oauth` URL with the exact registered callback `https://concierge.trendibizz.com/owner/social/oauth/callback` and a new state value.
- Facebook scopes: `pages_show_list,pages_manage_posts,pages_read_engagement`.
- Instagram Graph API with Facebook Login scopes: `pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish`.
- Meta public authorization URLs responded `HTTP 302` to `www.facebook.com` when checked without following redirects, without logging in or consenting. This confirms that the Meta login path is reachable but **does not prove app approval, a correct secret, or a successful token exchange**.
- Staging PostgreSQL currently has zero Concierge tenants and zero owner users; the synthetic Rust smoke-test tenant did not create an API tenant or user.
- Production API, staging API, and local Rust health endpoints all returned HTTP 200 after testing.
- Live social publishing remains disabled. Production services were not restarted or modified.

## Still needed
1. Provision a staging business and owner invitation against the isolated staging API using an authorized test owner's actual email. Do not copy production user databases or send invitation tokens via logs or Git.
2. Owner signs into `https://concierge.trendibizz.com/owner-ui`, clicks Connect Facebook and authorizes in Meta while the SocialSync app remains in Development mode.
3. Confirm the authorized Meta account is an app Administrator/Developer/Tester with appropriate Page access; inspect Meta's actual permission grants and verify authorized Facebook Page identity.
4. Repeat for Instagram professional account linked to an authorized Facebook Page, then test disconnect/reconnect and tenant isolation.
5. Obtain documented approval before enabling any real posting. Keep all publish flags false for this verification.

**Status:** OAuth URL construction verified against a live Meta login redirect; real owner consent and complete provider token exchange **not** yet verified.
