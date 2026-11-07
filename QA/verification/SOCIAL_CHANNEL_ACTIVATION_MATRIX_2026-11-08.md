# Trendi Concierge Social Channel Activation — verified 2026-11-08

## Single customer experience

All customer connections use **Concierge** under `https://concierge.trendibizz.com/owner-ui` and the same verified HTTPS callback path: `/owner/social/oauth/callback`. Each platform uses its own app client and official authorization service, but customers use a single owner portal and never supply passwords to Trendi.

All credentials stay private to the provider backend and are encrypted with tenant/account-bound labels. An app being configured is **not** a certified live integration. Content publishing remains operator-gated and disabled.

## Actual audited readiness

| Platform | Current backend | Missing for real customer connection |
|---|---|---|
| Facebook | Live OAuth success; Trendi Page 270235042840463 saved | Wider public customer deployment requires Meta review/advanced access |
| Instagram | Facebook-linked professional Graph API path updated: business-account relationship is accepted from Meta's professional-only Page field, rather than requiring a redundant IG identity endpoint | Real Instagram callback verification and account row still required |
| LinkedIn | Existing Rust member authorization-code flow, account encrypted and disconnected through owner API | Trendi LinkedIn developer app ID/secret, approved scopes, callback and role; organization posting needs Community Management authorization |
| TikTok | New Rust Login Kit OAuth start/finish, state, official user-info identity, encrypted token + refresh, tenant-scoped revoke, owner portal button | TikTok developer app, Login Kit Web approval, client key/secret and callback. Publishing requires separate Content Posting API approval and video.publish implementation; none enabled |
| Google Business Profile | Existing Rust OAuth and owner portal button | Google Cloud OAuth client, Business Profile API entitlement, authorized customer consent |
| Mastodon | Existing Rust OAuth and owner portal button | Instance origin and registered OAuth credentials |
| Bluesky | Connector exists, but owner onboarding/credential lifecycle not complete | Separate customer linking implementation and account authorization |
| YouTube | Not yet implemented as a standalone customer channel | Google Cloud YouTube Data API, OAuth/verification, account identity and video upload scope |
| Pinterest | Not yet implemented | Pinterest developer app, approved OAuth scopes and customer connection service |
| X | Not yet implemented | X developer application, API access/fee approval and customer authorization |

## Operator integration settings

**All exact redirect URLs:** `https://concierge.trendibizz.com/owner/social/oauth/callback`.

In the **private** Mac.hub `.private/oauth-staging/social.env`, set only the platform-specific required keys:
- LinkedIn: `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK`.
- TikTok: `SOCIAL_TIKTOK_CLIENT_KEY`, `SOCIAL_TIKTOK_CLIENT_SECRET`, `SOCIAL_TIKTOK_CALLBACK`.
- Google Business: inspect the existing `google_business.rs` env schema before adding provider credentials.
- Mastodon: inspect the existing `oauth.rs` env schema and ensure per-instance permissions.

Do NOT reuse Meta's SocialSync App Secret for LinkedIn, TikTok or Google. Each provider app is independent.

## Required acceptance per platform

1. Customer owner signs in under a tenant-scoped session and authorizes only requested scopes at the provider.
2. Server consumes a one-time tenant-bound OAuth state; exchanges code only on trusted backend, verifies account identity and saves encrypted access (and refresh, if provided).
3. Account appears for that tenant only, is absent from other tenants and can be disconnected; token renewal works for expiring providers.
4. No live publishing is enabled until authorized, reviewed, and independently exercised against provider sandbox/test accounts.
5. Production approval includes privacy policy, terms, data deletion, security, rollback and app review.

## Security and performance constraints

- Keep production CRM, LiveKit/Grok voice, and website untouched; staging Rust and API only.
- Do not run full Docker Rust builds on the 16 GB Mac.hub while production is live; use single-job native Rust incremental builds.
- Unrelated `QA/verification/office-shots/` is preserved.
- Instagram status cannot be marked connected until an actual encrypted account record exists; green sign-in alone is insufficient.
