## SocialSync / Concierge OAuth: staging activation gates (8 Nov 2026)

Meta UI observations: the **Enforce HTTPS** control appears greyed out. Treat it as Meta-managed; do not attempt a browser workaround. Web OAuth Login and Client OAuth Login are enabled. Existing redirect `https://trendibizz.github.io/SocialSync/` must remain until independently confirmed unused. Do not register a new callback until the Concierge owner portal is actually served at a verified public HTTPS origin.

Current running Mac.hub API (image created 6 Nov) returns HTTP 404 for `/owner-ui` and `/owner/social/oauth/callback`, although both routes exist in the checked-in implementation. Neither `api.trendibizz.com` nor `concierge.trendibizz.com` resolves in the tested environment; `trendibizz.com/owner/social/oauth/callback` returned 404. **This is not an activated OAuth callback.**

### Safe deployment architecture prepared

The root Compose file contains an opt-in `social` profile. The Rust social backend shares the API container's network namespace and binds exclusively to `127.0.0.1:4390`, with a private volume and live posting forced off. The API's social integration is disabled unless the operator explicitly enables it and supplies matching internal service credentials. The separate Rust Dockerfile builds the actual social-service binary; no production deployment was performed.

Source must be rebuilt and rolled to a **separate authorized staging API** first. Verify `/owner-ui` and `/owner/social/oauth/callback` both return HTTP 200 before touching Meta's registered redirects:

```bash
python3 scripts/verify-social-oauth-endpoints.py --origin https://YOUR-VERIFIED-API-HOST
```

Only after this passes should the exact `https://YOUR-VERIFIED-API-HOST/owner/social/oauth/callback` be added to Meta Facebook Login > Settings > Valid OAuth Redirect URIs. Preserve the GitHub Pages redirect and enable strict URI matching when all redirects are known and tested.

### Required owner / provider actions

1. Confirm which Trendi-owned HTTPS hostname / DNS zone to use for the owner portal, and grant access to the hosting/DNS system for staging. An existing working HTTPS host is preferable to inventing a subdomain.
2. In SocialSync > App Settings > Basic, configure the actual app domain, privacy policy and deletion instructions; grant the protected App Secret through Mac.hub's gitignored private secret file or approved secret manager. Never screenshot or paste the secret into chat.
3. Verify Facebook Login and Instagram Graph API scopes and approved app roles; request advanced access/app review for unrelated customers. Do not flip the whole app Live until approvals are complete.
4. Test two authorized customers, linked Pages/Instagram professional accounts, tenant isolation and unlink/relink. Publish only with separate explicit authorization.
5. Reconcile backups, monitoring and rollback before production deployment.

Status: deployment wiring and preflight code prepared; public HTTPS ingress and real Meta OAuth remain unverified. No production service, DNS, Meta app setting or existing redirect was changed.
