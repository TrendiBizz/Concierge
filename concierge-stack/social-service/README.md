# Concierge Social (Rust, independent implementation)

This is a lightweight service for one Concierge installation serving multiple
customers. It is not a Postiz fork, translation or derivative. Its connectors
are implemented against official network API specifications.

## Current status (2026-11-08)

**Meta SocialSync alignment:** Existing app ID 676274422041376 has Facebook Login and Instagram Graph API products. The new default is Graph API v27.0 (Meta release 2026-11-04), and Instagram is connected through Facebook Login to a linked professional Instagram account and managed Facebook Page. SOCIAL_INSTAGRAM_LOGIN_MODE=facebook is the default; standalone Instagram Login remains an explicit alternative. Network publishing remains disabled until authorization and real-provider tests. Local tests do not certify Meta approval.

Implemented and tested:

- Local HTTP server, two service roles, loopback-only binding.
- Customer-scoped SQLite customers, accounts, drafts and results, plus individually rotatable customer agent credentials.
- AES-256-GCM account-bound social credentials, no plaintext tokens in SQLite.
- Customer approval tokens: random, single-use, SHA-256 digest at rest,
  one hour expiry and bound to the approved post revision.
- Guardrails: platform limits, claim checking, forbidden phrases and warnings.
- Scheduler with defence-in-depth approval check and mock connector tests.
- Bluesky AT Protocol password-session posting connector for a private pilot.
  This is not an OAuth connect flow and is not ready for customer onboarding.
- REST API isolation: the Hermes key cannot approve customer posts.
- Explicit off-by-default network publishing, automated encrypted SQLite backup
  when the scheduled restic backup runs.

Not implemented or not yet validated:

- Bluesky/AT Protocol OAuth connect link with DPoP/PAR for customers;
  OAuth token refresh and revocation.
- Meta, Instagram, TikTok, X and other missing connectors. Mastodon and LinkedIn text-only
  publisher adapters are built but disabled by default and not provider-tested.
- LinkedIn OAuth implemented locally; not tested with a real registered provider app.
- Mastodon OAuth is implemented locally but has NOT been verified against
  a registered app or a consenting external test account.
- Media uploads, rich text facets and per-platform formatting.
- Inbound YES-reply verification and owner-to-tenant credential delegation;
  customer portal linking for Mastodon and LinkedIn is locally implemented,
  but real provider account validation and deployment are pending.
- Multi-tenant per-customer API credentials (current two keys are internal).
- Active network publication tests against a consenting test account.
- Automatic quarantine of posts interrupted while Publishing is implemented.
  Operator reconciliation UI, full audit/alerting and verified restart tests remain outstanding.
- Secure external ingress, monitoring, privacy/consent review, production launch.

**Do not connect real customers or turn on network publishing yet.**

## Current verification

33 offline Rust tests passing, plus a real local HTTP contract test with the
Concierge owner integration and a disposable database. This is NOT a live
network-posting test.

## Local tests

Run from this directory:

    cargo test --locked
    cargo fmt --check

The tests have no live network effects.

## Run locally (no publishing)

    ./run-local.sh

The first run creates `data/social.env` (private permissions, git-ignored)
with random encryption and service keys. The service is bound to
`127.0.0.1:4390`. Network publishing remains disabled. Never commit or paste
the service keys into chat.

## API overview

Read-only health endpoint:

    GET /health

Agent-key or Concierge-key routes:

    GET /v1/customers/:c/rules
    POST /v1/customers/:c/check
    POST /v1/customers/:c/posts
    GET /v1/customers/:c/posts
    PUT /v1/customers/:c/posts/:id
    POST /v1/customers/:c/posts/:id/submit
    GET /v1/customers/:c/accounts

Concierge-key only:

    POST /v1/customers
    PUT /v1/customers/:c/rules
    POST /v1/customers/:c/accounts
    POST /v1/customers/:c/posts/:id/approval-request
    POST /v1/customers/:c/approvals/:token/approve
    POST /v1/customers/:c/approvals/:token/reject

The last two routes are service-to-service endpoints, not public clickthrough
approval links. The customer approval capture and verification must be built
in Concierge before launch.

## Customer account linking (Mastodon staging path)

Concierge owner portal now offers a **Connect Mastodon** and a
**Disconnect** button. The browser opens the real provider approval in a
popup and returns to the existing owner session. No copy/paste, customer
API keys, stored customer passwords or browser-visible service secrets.

The first network uses operator-pinned Mastodon OAuth 2.0 authorization code
with PKCE-S256 and state. State is SHA-256-hashed in SQLite; the verifier
is tenant-bound AES-GCM-encrypted, expires in 10 minutes, and is used once.
Rust verifies the returned account on the provider API before storing an
encrypted token. Disconnect revokes the token using the provider's official
revoke endpoint before erasing credentials locally. Disabled by default.

**Operator-only configuration (never commit real values):**

- SOCIAL_MASTODON_ORIGIN: the exact HTTPS origin of the approved Mastodon
  instance, without a path (example: https://mastodon.social).
- SOCIAL_MASTODON_CLIENT_ID: client id from the registered Mastodon app.
- SOCIAL_MASTODON_CLIENT_SECRET: secret from that same app.
- SOCIAL_MASTODON_CALLBACK: the exact HTTPS callback registered with the
  app. It must return to the existing Concierge owner portal at
  `https://<approved-host>/owner-ui` (same origin as the portal).
- Register scopes `read:accounts write:statuses` on the Mastodon app.

Do not enable the Concierge social proxy or change DNS to test the
registration. Existing settings still default to disabled. Once separately
approved, use a disposable test tenant and a dedicated consenting Mastodon
test account. Verify successful linking, account identity, denial, expiry,
wrong-tenant state, reconnection, revocation and browser popup handling.

Current limits: one operator-configured Mastodon instance, not arbitrary
customer instances; no refresh support for other networks; no Mastodon
publishing connector; no real OAuth provider tests or staging deployment.
A customer account must not be marked live-ready on these tests alone.
Bluesky cannot reuse this simple OAuth implementation: its official flow
requires PAR, DPoP (including nonces) and verified DID identity.

Mastodon official documentation:
https://docs.joinmastodon.org/spec/oauth/
https://docs.joinmastodon.org/methods/oauth/
https://docs.joinmastodon.org/client/authorized/

## LinkedIn customer linking (staging implementation)

A second customer connect popup is implemented for LinkedIn member accounts.
It uses the official three-legged confidential-client OAuth flow with
cryptographically random, tenant-scoped one-use state, a 10-minute expiry,
access-token exchange and a bearer-authenticated `/v2/userinfo` lookup before
assigning the account to the current Concierge business. Unlike Mastodon,
LinkedIn's published member-flow documentation does not specify PKCE.

One operator-controlled Trendi LinkedIn developer app serves all authorized
customers. Customers only approve the familiar LinkedIn permissions screen.

Operator-only git-ignored environment values:
- `SOCIAL_LINKEDIN_CLIENT_ID`
- `SOCIAL_LINKEDIN_CLIENT_SECRET`
- `SOCIAL_LINKEDIN_CALLBACK` — exact HTTPS owner-portal callback, normally
  `https://<approved-host>/owner-ui`

Enable **Sign In with LinkedIn using OpenID Connect** and **Share on LinkedIn**
on the same developer app, with `openid profile w_member_social` scopes before
testing. The service fails closed if those scopes were not granted; no implicit
permission escalation. Verified tokens and any available refresh tokens are
encrypted and tenant-bound. Token expiry is recorded and expired accounts
cannot be used for new posting. Re-linking an identity updates its existing
account instead of creating a duplicate. Account permissions and their grant
and disconnect timestamps are persisted without copying access tokens.

Owner-side **Unlink LinkedIn** deletes the local credentials and prevents
future use. This is not represented as a provider-side revocation: owners
must also remove Trendi access from LinkedIn connected-app settings. The
ordinary LinkedIn OAuth flow does not document a general app-side revoke API.

Still unverified: actual LinkedIn app configuration and approval, real OAuth
redirect, token exchange, read identity, access scopes, refresh and live
publishing. No publishing permission should be claimed until a test account
has authorized and an explicit separate release gate is passed.

Official references:
- https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
- https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin

## Source and licensing

No Postiz source code has been copied or translated. Architectural concepts
are generic (one tenant per customer, approval gate, one connector per network).
The first connector was written from these specifications:

- https://atproto.com/guides/auth
- https://atproto.com/guides/sdk-auth
- https://atproto.com/guides/writing-data
- https://docs.bsky.app/docs/tutorials/creating-a-post

Postiz itself is AGPL-3.0 and is not a library or dependency of this service.

## Safety

- Network publishing is disabled unless a separate explicit configuration
  switch is enabled outside the provided launcher.
- A timeout after submitting a post is not automatically retried. It may have
  succeeded remotely; reconciliation is needed to avoid duplicates.
- Never treat a message `YES` as approval without checking the correct
  customer identity, post revision, message provenance and expiry.
- Each post is approved separately. Editing any content revokes approval.

## Disabled-by-default Mastodon and LinkedIn text publishing

The standalone Rust service has two additional independently implemented
text-only connectors alongside the existing Bluesky pilot. The scheduler still
requires the same tenant-bound owner approval and post revision, and never
auto-retries uncertain results.

Mastodon uses the operator-pinned HTTPS instance from
`SOCIAL_MASTODON_ORIGIN`, OAuth `write:statuses` token, official
`POST /api/v1/statuses`, and a deterministic hashed per-post idempotency key.
Text-only; no media. The account's verified instance must match the pinned
instance.

LinkedIn uses the logged-in member identity from OpenID Connect,
`w_member_social`, and the official `POST /rest/posts` API with the
`X-Restli-Protocol-Version: 2.0.0` and `Linkedin-Version: YYYYMM`
headers (default `202603`). It supports only public text posts by the
authenticated member, not company pages or media.

Three separate operator flags are needed to publish:
`SOCIAL_ENABLE_PUBLISH=true` globally, plus
`SOCIAL_ENABLE_MASTODON_PUBLISH=true` for Mastodon or
`SOCIAL_ENABLE_LINKEDIN_PUBLISH=true` for LinkedIn. None of these
are set by default. A malformed configured origin or LinkedIn version now
fails startup rather than leaving an unusable publishing task running.

The API implementations are based on:
- https://docs.joinmastodon.org/methods/statuses/
- https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

These are offline-tested request contracts only. No external account was
connected and no real post sent. Separate staging approval, genuine
provider permissions, consent, connected account, and end-to-end tests
remain mandatory before enabling either network.
