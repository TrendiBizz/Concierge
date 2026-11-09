# What it takes to publish to customers' social accounts from our own app

Date: 2026-11-07. Facts come from each network's OFFICIAL developer docs as read by research helpers. Marked "unconfirmed"
where a page failed to load or does not say. Approval times and fees are mostly NOT stated in the docs. Check each
network's page again before relying on any detail.

## The principle

Every customer authorises OUR app through the network's own OAuth screen. The approvals below are done ONCE for Trendi's app,
not once per customer. After approval, every customer links their account the same way, with no review each time.
"Free" here means no money to the network (X excepted); the cost is approval paperwork and build time.

## Per network

| Network | Works without approval? | What approval takes | Cost | Scheduling | Limits and notes |
|---|---|---|---|---|---|
| **Bluesky** | **Yes.** OAuth client with no review: the client id is an HTTPS URL to a metadata file | none | none stated | We build it | PKCE, PAR and DPoP are mandatory. Scope `atproto` (transitional `transition:generic` writes posts). Sessions last at most 2 weeks without re-login. |
| **Mastodon** | **Yes.** Register an app on each customer's instance | none described | none stated | Native (`scheduled_at`) | Scope `write:statuses`, `write:media`. A separate app registration per instance. |
| **LinkedIn, personal profile** | **Yes, self-serve implied**: add the "Share on LinkedIn" product to get `w_member_social` | not stated | none stated | We build it | `POST /v2/ugcPosts`. Daily limits shown may be stale. |
| **LinkedIn, company page** | No | Community Management API: Development tier, then Standard tier with a screencast of each use case. It is for partners who "manage LinkedIn company pages for clients". Scope `w_organization_social`; the connecting person must be a page admin or content admin. Review time unconfirmed (the review page returned 404). | none stated | We build it | `POST /rest/posts`. Use a current `Linkedin-Version` (202511 retires on 16 Nov 2026). |
| **Facebook Pages** | Development mode only: people with a ROLE on our app can connect | **Advanced Access: App Review plus Business Verification.** Permissions `pages_manage_posts`, `pages_read_engagement`, `pages_manage_engagement`, `pages_read_user_engagement`. App Review needs a use-case description and a screencast. | not stated | **Native**: `published=false` and `scheduled_publish_time` (10 minutes to 30 days ahead) | The connecting person needs page tasks CREATE_CONTENT, MANAGE, MODERATE. |
| **Instagram** | Development mode only (role holders) | Same Meta approval: Advanced Access, App Review, Business Verification. Permissions `instagram_business_basic` and `instagram_business_content_publish` (Business Login) or `instagram_content_publish` (Facebook Login). Customer must have a **Business or Creator** account. | not stated | **We build it** (no native scheduling in these docs) | 100 API posts per 24 hours (the same doc also says 50: inconsistent). Images JPEG only, media must be at a public URL. Two-step publish (`/media` then `/media_publish`). |
| **Threads** | Development mode: only invited "Threads testers" | `threads_content_publish` through App Review and the app must be published (Business Verification not mentioned on the Threads pages; the general Meta rule probably applies, unconfirmed) | not stated | not seen | 250 posts per 24 hours, text up to 500 characters. |
| **X** | Technically yes | No review described | **Pay per use, no free posting tier**: USD 0.015 per post, **USD 0.20 per post that contains a URL** (cents for small volumes) | We build it | OAuth 2.0 PKCE, scopes `tweet.write`, `users.read`, `offline.access`. Tokens last 2 hours without refresh. |
| **TikTok** | No for public posts | **Audit required**: until audited, posts are restricted to private viewing (error `unaudited_client_can_only_post_to_private_accounts`). Audit process unconfirmed (its page returned 401). Scopes `video.publish` (direct) and `video.upload` (drafts to the user's TikTok inbox). | not stated | Not described | Upload-to-inbox lets the user finish in the TikTok app. 6 requests per minute per user. Paid-partnership flag must be set. |
| **YouTube** | Unconfirmed | Scope `youtube.upload`. The compliance-audit page returned 404, so whether unverified projects are forced private is **unconfirmed** | not stated; uploads cost quota (100 calls a day by default) | `publishAt` not read | OAuth client credentials from Google Cloud. |
| **Google Business Profile** | No | Access request form ("Application for Basic API Access"). Needs a verified, active profile managed for **60+ days**, a website on the profile, and the applicant as owner or manager. Approval shows as 300 QPM quota. Scope `business.manage`. | not stated | Not described | Local posts: `POST .../localPosts` with call-to-action types BOOK, ORDER, SHOP, LEARN_MORE, SIGN_UP, CALL. No sandbox. |
| **Pinterest** | Trial only: pins visible only to their creator | Trial request, then Standard upgrade with a **video demo of the OAuth flow**; no time stated. New apps from 14 Sep 2026 may be denied some reads. | not stated | not read | Scopes and endpoint unconfirmed. |
| **Reddit** | Unconfirmed | Unconfirmed (its pages could not be read) | Unconfirmed | | Treat as out of scope until read directly. |

## What this means

1. **One approval unlocks three networks: Meta (Facebook Pages, Instagram, Threads).** It needs Business Verification of TRENDI LIMITED, a privacy policy URL, app review with screencasts, and (for production) a data-use checkup each year. It has the longest and least certain lead time, so it should start first.
2. **Can be built and used straight away, with no approval:** Bluesky, Mastodon, LinkedIn personal profiles. X needs no approval but costs cents per post.
3. **Approvals to apply for in parallel:** LinkedIn Community Management (company pages), Google Business Profile access, TikTok audit, Pinterest Standard.
4. Until approvals land, a posting service that already holds approved apps (Upload-Post free plan, 2 profiles) can carry the first one or two customers (see `SOCIAL-AND-HERMES-PLAN.md`).
5. **Privacy policy.** Meta and others require a published privacy policy and a data-deletion route. The site's Privacy page is still a lawyer draft; approvals depend on it.

## Where the connectors live

Customers' tokens are held by SocialSync (our code), not by Hermes. SocialSync gets, per network: an OAuth start and callback,
encrypted token storage per customer, refresh, a publish adapter, and a scheduler (Instagram and others have no native
scheduling). Hermes calls SocialSync (draft, check against guardrails, request approval, schedule). This keeps credentials out
of the agent and keeps one place that enforces the guardrails and the customer's approval.

## Build order (free first, by lead time)

1. Start the approval applications now: Meta (Business Verification, then App Review), LinkedIn Community Management, Google
   Business Profile, TikTok, Pinterest. I can prepare the submission texts and screencast scripts; the company documents
   and the privacy policy are Jo's.
2. SocialSync groundwork: under git, backed up, then a connector framework (OAuth, encrypted tokens, scheduler).
3. Connectors with no approval wait: Bluesky, Mastodon, LinkedIn personal, then X.
4. Meta, LinkedIn pages, GBP, TikTok, Pinterest connectors as each approval arrives (develop in each network's development mode with test accounts first).
5. Guardrails and the approval gate in front of every publish (SocialSync's core idea).
