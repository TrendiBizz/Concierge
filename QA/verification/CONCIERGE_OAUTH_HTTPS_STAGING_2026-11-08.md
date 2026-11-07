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

The Rust service was tested locally in earlier commits, but its large Docker release builder pull caused resource contention and was **canceled** to protect production health. The staging public API was not redeployed to enable the social service. The private staging social env file is prepared, but the separate Rust backend is not running here. Provider connection buttons remain unavailable until the private social backend and Meta App Secret are activated. Do not call live Meta OAuth certified.

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
4. Run the Rust social backend in staging with the matching isolated key, then enable only the staging API integration and test tenant-scoped OAuth. Leave publishing disabled.
5. Independently certify two customer logins and permissions before production approval.

## Rollback without affecting live CRM/chat

Stop the new LaunchAgent and the two `concierge-oauth-staging-*` containers. Remove ONLY the new Cloudflare tunnel DNS record if retiring this staging hostname; leave existing `crm-trendibizz` tunnel, website DNS, public chat, CRM, database volumes and production API unchanged. Keep the private staging data for controlled recovery unless authorized to delete it.

**Not done:** Real customer OAuth consent, Meta App Secret activation, production social publishing, final customer acceptance or deployment. This is verified HTTPS staging infrastructure, not production certification.
