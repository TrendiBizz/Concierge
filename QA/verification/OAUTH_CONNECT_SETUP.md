# Concierge customer social OAuth activation

This is the operator setup for the **existing** Rust service and Concierge owner portal, not a separate backend.

## Exact callback

Register the following **exact** HTTPS redirect URI in every provider developer application:

`https://YOUR-CONCIERGE-API-HOST/owner/social/oauth/callback`

The callback must resolve to the Concierge API hosting `/owner-ui`. HTTPS, hostname, and path must match the URL registered with the provider. The callback forwards an authorization code only to the same-origin opener, which checks state and exchanges it server-side. It does not retain credentials.

## Configure the Rust service (private environment only)

- `SOCIAL_CONCIERGE_KEY`: random 32+ character shared API-to-Rust service key.
- `SOCIAL_AGENT_KEY`: separate random 32+ character agent key.
- `SOCIAL_VAULT_KEY`: base64 32-byte AES-GCM key, held in an approved secret store and kept through restores.
- `SOCIAL_DB`: private persistent SQLite file path.
- `SOCIAL_BIND`: `127.0.0.1:4390` on the service host. Must not listen publicly.
- `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK`.
- `SOCIAL_MASTODON_ORIGIN` (one operator-pinned HTTPS instance), `SOCIAL_MASTODON_CLIENT_ID`, `SOCIAL_MASTODON_CLIENT_SECRET`, `SOCIAL_MASTODON_CALLBACK`.

The Concierge API must also have `SOCIAL_SERVICE_ENABLED=true`, `SOCIAL_CONCIERGE_KEY` matching Rust and `SOCIAL_SERVICE_URL=http://127.0.0.1:4390` if reachable locally. The Docker-to-host path must be verified independently.

**Do not put any real key in Git or build output.** Keep `SOCIAL_ENABLE_PUBLISH=false` and all per-network publish switches off until an operator approves and audits real tests.

## Provider gates

**LinkedIn:** Create/verify a developer app, register exact redirect URI, enable `Sign In with LinkedIn using OpenID Connect` and obtain `w_member_social` access. Current code requests `openid profile w_member_social`. A scope not approved for the app causes a provider error. Access tokens are encrypted, linked to the verified profile and blocked on expiry; refresh is only available if LinkedIn grants the applicable partner feature. Local unlink destroys stored credentials; customers withdraw remaining consent in LinkedIn connected-app settings.

**Mastodon:** Register an application on the selected server with the exact callback and `read:accounts write:statuses` scopes. OAuth authorization code uses S256 PKCE, tenant-bound state, encrypted tokens and provider-side revoke.

**Facebook/Instagram and other major networks:** NOT IMPLEMENTED as customer OAuth adapters by this document. Their official customer-login products, application permissions and tests must be implemented independently before enabling them. In particular, Instagram business/creator publishing permissions are not interchangeable with Facebook Page permissions.

## Evidence required before activating a provider

1. Authorised customer account signs into the provider via the Concierge owner portal.
2. App redirect and token exchange succeed with the expected tenant and scope.
3. Owner sees the verified account identity; a different tenant cannot see or unlink it.
4. Disconnect and reconnect are tested. Short-lived access expiry and refresh/re-auth are verified.
5. Approved test post is externally confirmed (separate explicit publishing approval).
6. Operator records consent, receipts and rollback and tests with two different customers.

The `GET /owner/social/status` endpoint reports whether the **configuration is valid** for LinkedIn and Mastodon, not whether an account or app review has been provider-approved. Never interpret a true configuration flag as production certification.
