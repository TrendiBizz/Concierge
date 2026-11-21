# Trendi DigitalOcean production

The public website, Concierge API, isolated social vault and Twenty CRM run at
`152.42.239.240` in `/opt/trendi/releases/20261108-vps`. Public URLs stay unchanged:

- Website: https://trendibizz.com/concierge
- Owner portal: https://concierge.trendibizz.com/owner-ui
- Twenty CRM: https://crm.trendibizz.com
- Widget/API: https://chat.trendibizz.com (public routes only)

The original website worker and static files are served by `website.mjs`. No
Cloudflare-specific business logic was rewritten. Caddy routes by hostname and
allows only the existing public API/owner paths. The container engine (Podman) publishes only loopback
ports 8000 and 8080; PostgreSQL, Redis and the social vault have no public ports.
Two existing Cloudflare Tunnel identities terminate traffic on this VPS. Do not
run their old Mac connectors concurrently against independent database copies.

The machine has 8 GB RAM, 2 vCPUs and 160 GB disk, plus 2 GB swap. Production runs on Podman (since 2026-11-17); the Docker engine is disabled and not used.
Every production container has `restart: unless-stopped` and comes back after a reboot via
`podman-restart.service` (override `scripts/vps/podman-restart.service.d/unless-stopped.conf`).

## Operate

Run on the VPS as root. The root-only `compose.env` selects the website source.

Do not run container commands by hand. Releases go only through `scripts/vps/deploy-api.sh`,
`deploy-site.sh` and `sync-tooling.sh`, and are proved with `verify-deploy.sh`; the container
steps live inside those scripts (`redeploy-api.sh` builds the API/social images before changing
their running containers). Recreate `social` whenever
recreating `api`: they share a private network namespace. API dependencies are
locked to the verified production versions; Containerfile-specific ignore files
exclude private settings, keys, dumps and unrelated source from build contexts.

Secrets live in `/opt/trendi/shared`, mode 700 directory / 600 files. Never commit
that directory or print Compose's resolved environment. The existing PageSpeed credential is retained in `website.env`. Social tokens stay
ciphertext, with the original vault key preserved in `social.env`. SMTP uses the
existing Brevo account with STARTTLS on port 2525 (DigitalOcean blocks 587).

## Backups and restore verification

Existing encrypted Cloudflare R2/restic repository and password are preserved.
The VPS backup includes both PostgreSQL dumps, online SQLite social backup, CRM
uploads, Redis queue snapshot, legacy voice recovery files, the release and
private runtime/recovery settings. Backup failure exits nonzero; it cannot
silently initialize a new repository. Existing snapshots are not pruned.

- `trendi-backup.timer`: daily 03:15 Pacific/Auckland.
- `trendi-restore-test.timer`: first of the month 03:45 Pacific/Auckland.
- Manual: `systemctl start trendi-backup.service` or
  `systemctl start trendi-restore-test.service`.
- Status: `systemctl list-timers 'trendi-*'` and
  `journalctl -u trendi-backup.service -u trendi-restore-test.service`.

The restore check downloads the newest VPS snapshot, verifies SQLite and uploads,
and restores **both** PostgreSQL databases into a disposable pgvector/Postgres 16
container with no network, published ports or production volumes. It removes its
temporary restored secret files and test database afterwards. Preserve the Mac's
existing private backup configuration/password separately for disaster recovery.

## Migration and rollback

Final cutover dumps and per-table record-count manifests are in
`/opt/trendi/backups/*-final*`, also retained privately on the Mac. All 23 Concierge
and 121 Twenty tables matched after restoration. The imported Concierge sequences
were advanced with `repair-sequences.sql` because several legacy sequences were
behind their existing row IDs. Run this after future restores of those old dumps.

The source Mac production API and Twenty server/worker containers are stopped;
their original databases, volumes, image and configuration remain available.
Old main/owner tunnel connectors were stopped; the owner connector and old Mac
backup/restore schedules are disabled across future logins. Other Mac applications remain
untouched. Apex and www CNAMEs point to the existing main tunnel; mail MX/TXT/CAA
records were preserved. The previous Pages deployment remains available.

**Do not simply start the stale Mac apps as rollback.** First stop VPS writers,
make fresh VPS dumps/social/storage/Redis backups, restore those onto the intended
rollback host, and verify records. Stop VPS tunnel connectors before restarting
Mac connectors. For website-only rollback, restore apex/www CNAME targets from
the private pre-cutover DNS snapshot (`trendi-ezj.pages.dev`) after verifying the
Pages release. Never delete production volumes as part of rollback.

## Channel activation

Website AI chat and approved outbound email were tested through the public URLs.
Authenticated signed-email intake creates CRM enquiries and owner-reviewed reply
drafts. Domain inbox routing remains with the existing mail host: automatic
mailbox forwarding to that intake is a separate pending setup. Phone/SMS provider
credentials and live channel tests are also pending. Legacy voice configuration
is preserved for recovery; no untested phone adapter is silently activated.
Social account connections are preserved; publishing remains disabled.

Cloudflare Bot Fight Mode and client-side script monitoring are enabled. Managed
WAF, browser integrity checking, DDoS protection, HTTPS redirects, HSTS and TLS 1.3
are active; minimum TLS is 1.2. Search/AI crawler policies allow indexing, and Bot
Preference Sync advertises those policies in robots.txt. Recheck webhook and
owner access whenever changing bot policies: Free Bot Fight Mode cannot be
selectively skipped by WAF rules.

## Hermes

Removed 2026-11-21. Box cleanup: `remove-hermes-leftovers.sh`; tables dropped by migration 0002 (`migrate-api.sh`); dump taken by `hermes-db-backup.sh`.

## Dev leftovers

Removed 2026-11-21. Box cleanup: `remove-dev-leftovers.sh` (lists and confirms no overlap with production, backs up non-empty volumes to `/opt/trendi/releases/20261108-vps/removed/20261121/dev-volumes/`, removes `dev-*` containers/volumes/networks/unused images, and removes `containerd` only when Podman does not depend on it).

## Grok SIP telephone activation

Website/portal voice uses browser audio and needs no telephone number or SIP
connection. Optional carrier calls have separate activation requirements; see
[PHONE_SETUP.md](PHONE_SETUP.md). Rebuilding the API never provisions a number.

Record the source revision when building the production API:

`redeploy-api.sh` builds the production API image; the source revision is recorded by the build.

The resulting image records `org.opencontainers.image.revision`. Archive the
source, private runtime env and database before deploying migrations. Recreate
both API and social together because social shares API's network namespace.
