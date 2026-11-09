# Run the integrated Trendi website and Concierge

Double-click `Start Trendi Local.command` in the product repository. It starts the
current website, current API, current native Rust social service and the existing
website checkers behind **http://127.0.0.1:8793/**. Docker Desktop must already be
running. The launcher builds from source, verifies dependency parity and compares
every application/static file in the API image with the checkout before use.

The launcher opens `/admin-ui` and copies the private local admin key to the
clipboard. Paste into **Admin token**, then click **Sign in**. The key is also in
`.private/local-stack/admin-token.txt`; never share or commit it.

Use **Add customer** to create a separate business and its private owner invitation.
The customer opens that local invitation, chooses their own password and is signed
into the correct workspace. Local invitations are usable only on this Mac. The
website's **Customer sign-in** goes to the local owner portal. **Get Concierge**
remains the reviewed setup-request form; it does not silently provision a customer.

The starter **Trendi local workspace** contains the actual website's extracted
Concierge, SEO and penetration-testing information, embedded with the real bundled
model. It contains no sample leads or bookings. The startup import runs only when
there is no knowledge; subsequent starts preserve business edits and saved data.
Bookings made here use a local calendar, not a promised Google/Microsoft sync.

The local API reuses the already configured text AI endpoint from the existing
staging configuration, or the running production API if the OAuth sandbox has no
AI key. Keys stay private. Startup and the smoke suite make no AI completion or
voice requests. Interacting with chat uses that configured provider normally.

## Runtime boundaries

| Component | Local runtime |
| --- | --- |
| Website, customer portal, admin, widget, APIs and ICS | `http://127.0.0.1:8793/` |
| PostgreSQL | `trendi-local-db-1`, private Docker network, persistent `trendi-local_database` volume |
| Latest API | `trendi-local-api-1`, image `concierge-api:trendi-local` |
| Latest Rust social draft/approval backend | Native process at `127.0.0.1:4391`, separate private SQLite |
| Existing SEO/security worker | `trendi-local-tools-1`, exact website `deploy_known_good/_worker.js` |
| Reverse proxy | `trendi-local-web-1`, original website files mounted read-only |

Existing production API `8000`, OAuth staging `8001`, connected social service
`4390`, Twenty CRM, LiveKit/Grok voice, recordings and public Cloudflare routing are
not modified or restarted. Real connected social accounts remain in the existing
HTTPS owner portal at `https://concierge.trendibizz.com/owner-ui`; they are not copied
into this separate local database. No new OAuth consent is needed to preserve them.
The local social backend supports drafts and permissions but has no provider OAuth
credentials. Live social publishing, outbound email/SMS/campaigns, PSTN and
recordings remain disabled locally. The local database is not connected to Twenty.

This is a runnable local integration, not a production rollout or certification of
external delivery, customer-specific CRM destinations, two-way calendar sync or
provider approvals. Those still require the controlled live acceptance/cutover
described in the verification handoffs. No production deployment occurs here.

Double-click `Stop Trendi Local.command` to stop only these owned local services;
the database and private settings remain. Start again with the Start command.
Do not use `docker compose down -v` unless intentionally deleting local data.
The website's source defaults to the sibling `trendi-site-web` checkout; set
`TRENDI_WEBSITE` before running `scripts/start-local.sh` to use another checkout.

## Repeat verification

From this repository:

```sh
export TRENDI_WEBSITE=/Users/jo/work-staging/trendi-site-web
docker compose --env-file /dev/null -f scripts/local/compose.yml exec -T api python - < scripts/local/smoke.py
```

The suite refuses a non-local database configuration. It creates two uniquely named
QA businesses, exercises invitations, sign-in, tenant isolation, real knowledge
embedding/replacement, Rust connectivity, booking confirmation/concurrency, ICS,
pipeline and logout through the gateway, then removes only those QA businesses.
It also checks preserved website pages and original worker routes. It makes no paid
provider requests, publishing, live calls or message delivery.

Verified during integration: **56 runtime checks**, **73 Python unit/config checks**,
and **10 existing website client tests** passed. Real browser verification confirmed
the widget opens with the local business greeting and the authenticated admin
dashboard presents the customer-creation form. No AI response or live provider
workflow was exercised as part of these checks.
