# Concierge OAuth HTTPS staging — actual deployment (8 November 2026)

## Verified URL

- Owner portal: **https://concierge.trendibizz.com/owner-ui**
- Meta OAuth callback: **https://concierge.trendibizz.com/owner/social/oauth/callback**
- The exact callback must be appended to the existing SocialSync Facebook Login **Valid OAuth Redirect URIs** list; preserve the legacy `https://trendibizz.github.io/SocialSync/` redirect until independently retired.
- Authenticated owner APIs are exposed only below `/owner/*`. All other paths through this tunnel return 404.
- HTTPS was confirmed with Cloudflare's certificate verification (`TLS=0`) for the portal and callback. Unauthenticated `/owner/social/status` returned 401, and `/healthz`, `/docs`, and non-owner API routes returned 404.
- Public Cloudflare DNS resolver resolved `concierge.trendibizz.com`; Mac.hub's system DNS was temporarily stale, so tests used `curl --resolve` and full TLS verification. Do **not** disable TLS checks.

## Hosting / live-service separation

This runs on **Mac.hub**, not the public `trendi-site` web host.

Existing tunnel `crm-trendibizz` (UUID `c25e268f-ce3b-4ca6-bb0a-85d538bee4f3`) was NOT modified or restarted. A distinct tunnel was created:

- Cloudflare tunnel: `concierge-oauth-staging`
- ID: `56b212ec-c55c-44e7-bbc2-40d76b44aaa7`
- Config: `~/.cloudflared/concierge-oauth-staging.yml` (private)
- Credentials: `~/.cloudflared/56b212ec-c55c-44e7-bbc2-40d76b44aaa7.json` (private; DO NOT commit)
- LaunchAgent: `~/Library/LaunchAgents/com.trendi.concierge-oauth-staging.plist` (RunAtLoad + KeepAlive)
- DNS: Cloudflare Tunnel CNAME route for `concierge.trendibizz.com`.

The new tunnel routes only `^/(owner-ui|owner(?:/.*)?)$` to the dedicated staging API on `127.0.0.1:8001`. The existing public chat and CRM routes remain separate.

## Isolated staging containers

- `concierge-oauth-staging-api`: freshly built `concierge-api:oauth-staging-20261108`, bound only to `127.0.0.1:8001`.
- `concierge-oauth-staging-db`: independent PostgreSQL `concierge_staging` using `pgvector/pgvector:pg16`, private named volume `concierge_oauth_staging_pg`.
- Private network: `concierge-oauth-staging` (internal database connection). The API additionally has the default bridge attachment for local port forwarding.
- Private environment files: `.private/oauth-staging/api.env`, `.private/oauth-staging/postgres.env`, `.private/oauth-staging/social.env`, each mode `0600`. Secret values are NOT in Git.
- Staging has outbox, paid/phone, inbound email, SMS and publishing disabled. No production customer database was attached or copied.

## Social OAuth backend status

The Rust service's large Docker release build was **canceled** to protect production health on the 16 GB Mac. Instead, the already-compiled native Rust binary was started as a dedicated launch agent:
- `com.trendi.concierge-oauth-social-staging` (on Mac.hub, local `127.0.0.1:4390`)
- Private startup wrapper `.private/oauth-staging/run-social-staging.sh` with permission 0700
- Private staging database `.private/oauth-staging/social.db`
- Secret values read only from `.private/oauth-staging/social.env` with permission 0600

The staging API was recreated **without changing the production API**, using `SOCIAL_SERVICE_ENABLED=true`, `SOCIAL_SERVICE_URL=http://host.docker.internal:4390`, and a matching private API-to-Rust key. Docker's host gateway reaches the native service; publishing is explicitly disabled. End-to-end API-to-Rust provider readiness returned `facebook=true`, `instagram=true`, and other providers false as expected.

The user-supplied SocialSync App Secret has been stored in private staging configuration without disclosure. HTTPS portal and callback both passed public Cloudflare checks, and production `/healthz` returned 200. **Provider readiness means credentials and configuration are present, not that Meta has accepted the redirect or customer consent.** Before final certification, use an authorized real account to complete the Meta OAuth browser flow, check permissions and account discovery, and test unlink/relink. No live posting was enabled.

Resource note: Mac.hub had approximately 17 GB swap in use with an idle ~5.2 GB LM Studio model and Docker VM. Do not rebuild the Rust image on this host while production is running without strict resource constraints.

After canceling the large build, the existing production API was checked and returned to `healthy` without restart.

## Checks

From the repo checkout on Mac.hub:

```bash
python3 scripts/verify-social-oauth-endpoints.py --origin https://concierge.trendibizz.com --edge-ip 104.21.57.104
```

The explicit edge IP is an optional workaround only for a stale local DNS cache. Do not treat it as a permanent hard-coded endpoint. Once local DNS resolves, omit `--edge-ip`.

Before using Meta, check both portal and callback return 200, the private API remains limited, and the provider permission grants are correct.

## Remaining owner-only tasks

1. In existing SocialSync Meta app (`676274422041376`), Facebook Login > Settings, **add** the exact URL `https://concierge.trendibizz.com/owner/social/oauth/callback` under Valid OAuth Redirect URIs. **Do not delete** `https://trendibizz.github.io/SocialSync/`.
2. In App Settings > Basic, reveal App Secret and enter it ONLY into the private `SOCIAL_FACEBOOK_CLIENT_SECRET` configuration through an approved secure local process. Never paste into chat or Git.
3. Confirm SocialSync's Meta app roles, Facebook Page grants, linked Instagram professional account and applicable advanced access / review. Stay in Development mode for the pilot.
4. The native Rust social backend and staging API integration are now active and locally verified. Test real tenant-scoped OAuth in Meta after registering the callback; leave publishing disabled.
5. Independently certify two customer logins and permissions before production approval.

## Rollback without affecting live CRM/chat

Stop the new LaunchAgent and the two `concierge-oauth-staging-*` containers. Remove ONLY the new Cloudflare tunnel DNS record if retiring this staging hostname; leave existing `crm-trendibizz` tunnel, website DNS, public chat, CRM, database volumes and production API unchanged. Keep the private staging data for controlled recovery unless authorized to delete it.

**Not done:** Real customer OAuth consent, Meta App Secret activation, production social publishing, final customer acceptance or deployment. This is verified HTTPS staging infrastructure, not production certification.
