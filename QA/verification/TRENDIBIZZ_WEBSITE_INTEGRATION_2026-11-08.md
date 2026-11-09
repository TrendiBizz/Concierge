# Existing TrendiBizz website integration — 8 November 2026

Implemented source integration; no production deployment, hosting move or paid-provider action.

## Customer experience and source ownership

The existing trendibizz.com website remains the front door. Concierge is the flagship; SEO and AI visibility and penetration testing remain distinct services. Website source is Trendiisales/trendi-site, branch concierge-site, commit fad74d3. All product code remains in TrendiBizz/Concierge, branch integration/concierge-v1. No backend was copied into the website and no new repository or public brand was created.

Website integration includes `/concierge`, a reviewed setup request at `/concierge-start`, `/concierge/sign-in` redirecting to the existing secure owner host, the shared website assistant, consistent company/contact metadata and retained service pages. The SEO and pentesting main content is byte-for-byte unchanged against the prior website branch. Existing SEO payment links remain intact; no new Concierge checkout or subscription was activated.

This product change brands the existing authenticated owner portal with the Trendi mark and links to the same public services. All form/control IDs are retained, and no login, invitation, tenant, OAuth, publishing, phone, email, CRM or recording logic changed. The widget now exposes readiness/open events; opening only shows the interface and does not send a message, start voice or access the microphone. The website supports the older deployed widget during rollout.

## Executed verification

- Website: 10 offline client contracts passed; all JSON-LD parses; five primary pages have one H1, unique IDs, balanced sections and valid local script references.
- Product: one real-widget-source host-control regression passed with an in-memory DOM and stubbed configuration; 14 owner/social API tests passed; owner inline JavaScript syntax valid and original form/control IDs retained.
- Repository-boundary check passed against the website worktree. Both modified GitHub Actions YAML files parse.
- Website candidate: 69 public asset paths, retained Functions worker/routes and header/redirect form fields. Final preflight 37 passed, zero failed. All four public no-key threat feeds loaded after restoring the original Trendi helper. A synthetic local-blocklist regression failed closed as intended. Six scanner notices remain: reviewed new JS files, existing example host names, and previously approved chat CSP entries.
- Existing live website SEO gate: 21 passed, zero failed, zero warnings. This is baseline verification, not a new deployment.
- Browser UI/visual verification is blocked: the browser security gate reported declined access to the local preview. No headless browser, alternate surface or indirect browser control was used to bypass it. New visual layouts and real browser click-through remain unverified.

## Prepared application artifact

`concierge-api:trendi-integration-20261108` was built locally with `api/Dockerfile.integration`, using the existing dependency image and no build network. Both `/srv/app` and requirements in the base were checked against canonical source. The candidate's 47 app/static files were hash-verified against canonical source from a disposable, network-isolated, read-only container without credentials or production data. No dependency/model download, live container replacement or service restart.

The standalone build helper assumes the verified base image is already present. For a new machine or changed requirements, use the normal api/Dockerfile and validate dependencies afresh. The new .dockerignore excludes private environment files, caches and local databases from the build context.

## Production cutover boundaries

The owner host still serves the isolated staging API on 8001. The current production API on 8000 still uses its existing image and Compose project under /Users/jo/concierge. The new image is only a candidate. Do not silently promote the owner host or copy tenant-bound encrypted OAuth credentials into a different tenant/database. Review the runtime configuration, schema/backups, tenant mapping and the existing provider/legal activation gates before a separately approved cutover.

The existing connected Facebook, Instagram, LinkedIn and TikTok staging accounts are preserved. No unlink/relink, live social post, email/SMS send, phone call or recording was initiated. LiveKit/Grok, CRM, Docker volumes and production processes were not changed. Untracked office-shots and tiktok-review media remain untouched and excluded from commits.

Full website evidence and the local candidate bundle path are in research/TRENDIBIZZ_CONCIERGE_INTEGRATION_2026-11-08.md in the website commit above. Website CI now runs on concierge-site pushes; product CI includes the new widget contract. CI results are distinct from local check results.
