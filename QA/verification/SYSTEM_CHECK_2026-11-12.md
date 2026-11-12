# Full systems check — 2026-11-12 20:20 NZ (07:20 UTC)

Operator asked for a full systems check for outstanding issues / potential problems beyond the
go-live hardening checklist. This is the result. Everything below was run against the live VPS
(`152.42.239.240`) and the local checkout at `25c42eb`+docs (`4943cf9`).

## Verdict

**Green where the previous sessions said it was green** — 44/44 health checks, 604 API tests,
Rust 6/6 + 6/6, no 5xx, no crash loops, TLS/DNS sane, git clean, no committed secrets.
**Four things are not green or not what the docs claim**, plus the deferred go-live list.

## P1 — fix before real customers

### 1. Worker inbound secret is plain text — and it was read in full during this check
`git` evidence: `QA/verification/GO_LIVE_HARDENING.md` §1. Live API evidence
(`GET /accounts/{acct}/workers/scripts/concierge-inbound-worker/settings`):

```
CONCIERGE_INBOUND_SECRET  type=plain_text  (value returned)
CONCIERGE_INBOUND_URL     type=plain_text
FORWARD_TO                type=plain_text  (kiwi18@gmail.com)
```

The value was printed while verifying the binding type, so it is now in this session's log as
well as readable by any Workers-read principal. **Treat it as rotated-now-or-not-at-all:**
rotate `INBOUND_CLOUDFLARE_SECRET` in `/opt/trendi/shared/api.env` and the Worker binding in the
same sitting, and make the binding a **Secret**. Alternative that fixes both: create a new
secret, deploy the Worker, restart `api`, send a test email, confirm a draft.

Also note `FORWARD_TO` is a plain-text personal address (`kiwi18@gmail.com`) — the Worker
forwards every unmatched inbound address there. Decide whether that should survive go-live.

### 2. Uptime Kuma is running but has ZERO monitors
`/app/data/kuma.db` → `select count(*) from monitor` = **0**. The status page API returns
`{"heartbeatList":{},"uptimeList":{}}`. The healthcheck still reports `aux:kuma HTTP 302` as
OK, so the monitor-of-the-monitor cannot tell. Monitoring is currently healthcheck.py (VPS, every
5 min) + the GitHub Actions uptime probe (every 20 min) — both real. Kuma adds nothing and gives
false assurance. Either configure its monitors or stop/remove the container.

### 3. Device-SMS receipts are lost during every deploy; 10 owner alerts are stuck forever
Gateway log, 24 h: **42 requests to `/api/v1/device-sms/receipt`, 42 × 502**, every one
`tcp: lookup api on 127.0.0.11:53: server misbehaving` — Caddy cannot resolve `api` during the
brief window the api container is being recreated. The bursts are retries (~5 attempts over
~13 s) and they stop before the api is healthy again, so the receipt is lost.

Consequence, DB evidence:

```
outbox: status=awaiting_receipt, 10 rows, kind=owner_alert,
        tenant=trendi-oauth-staging, created 2026-11-11 02:40 → 2026-11-12 04:44, last_error=''
device_sms_jobs: status=queued 10 (max 2026-11-12 04:44)
```

Nothing reconciles `awaiting_receipt`. `device_sms.py` only re-claims `claimed` jobs older than
5 minutes; an outbox row waiting for a receipt that will never arrive stays "in flight" forever.
For a single tenant this is cosmetic; at go-live it is silent loss of customer-facing owner
alerts. Fix options: (a) Caddy upstream with a static address or retry/`lb_try_duration` so a
DNS blip does not 502; (b) a sweeper that fails `awaiting_receipt` rows after N minutes with a
visible "receipt never arrived" reason; (c) make the phone connector retry with backoff past the
deploy window.

The endpoint itself is healthy — a direct unauthenticated POST now returns 401 in 0.2 s.

## P2 — should fix, not go-live blockers

### 4. Host hardening
- `ufw` **inactive**; `fail2ban` **inactive**.
- `PermitRootLogin yes` (should be `prohibit-password`/`no`) — key-only in practice.
- `PasswordAuthentication` is ambiguous: `50-cloud-init.conf` says `yes`,
  `60-cloudimg-settings.conf` says `no` (lexical last wins → effectively no). Set it explicitly
  in one drop-in and remove the other.
- Only public listener is `:22`; everything else is `127.0.0.1` + Cloudflare tunnels. 12 packages
  upgradable (unattended-upgrades active).
- `docker inspect`-style secret exposure is unchanged (xAI key still to rotate — carried item).

### 5. Backups are young and local-only
Last full backup `2026-11-11 14:30 UTC`, 59 MB; cron `30 14 * * *`; retention keeps 14. The
script has **no lock logic**, so the stale `backup.lock` / `auxiliary-backup.lock` files from
2026-11-11 are harmless but misleading — delete them. Still no offsite copy (known outstanding).

### 6. Cosmetics / cleanup
- `email-auth` builds with 2 `unused_assignments` warnings (`any_pass |= passed`).
- Scratch tenants still present: `concierge-test`, `trendi-oauth-staging`, `trendi-meta-review`
  (go-live checklist §5).
- `chat.trendibizz.com/` → 404 by design (Caddy path allowlist); widget paths 200.

## What passed (evidence)

- **Health**: rerun of `scripts/vps/healthcheck.sh` → `44 ok / 0 warn / 0 fail`, exit 0.
- **Containers**: 21 up, api + email-auth healthy, zero restarts, gateway 51 min, Kuma up.
- **Tests**: API **604 passed, 1 deselected** (CI env, `not hangs_on_py312`); Rust
  social-service **all pass**; email-auth **6/6**.
- **Runtime**: api 5xx in 6 h = 0; no error/traceback lines in api, email-auth, social, website,
  CRM, Kuma in 2 h; CRM `200`, website `200`, Kuma `302`, studio `200`.
- **Edge**: TLS `notAfter 2027-01-22`; all four public URLs answer expected codes.
- **Email auth**: DMARC `p=quarantine; rua=mailto:rua@dmarc.brevo.com`; SPF `~all` with Brevo +
  hosting + Cloudflare includes; DKIM `brevo1._domainkey` published (CNAME to Brevo); MX
  Cloudflare.
- **Cron**: backups 14:30, inbound-chain guard hourly :07 (all 5 tenants OK), healthcheck every
  5 min.
- **Repo**: working tree clean, no tracked env/key/secret files, `.env*` ignored, no private-key
  blocks.
- **Inbound**: 10 `received`, 1 `inbound_rejected` in 24 h — the rejection is the known synthetic
  bounce DSN to the scratch reply address from the guard test, expected.

## Recommended order
1. Rotate `INBOUND_CLOUDFLARE_SECRET` + make it a Worker Secret (this also clears the P1 leak).
2. Fix the SMS receipt path: Caddy upstream stability and/or an `awaiting_receipt` sweeper; clear
   the 10 stuck rows deliberately.
3. Configure Kuma monitors or remove Kuma.
4. Host hardening drop-in (ufw, fail2ban, root login, password auth explicit).
5. Then work through `GO_LIVE_HARDENING.md` §2–§6.

## Changes applied — 2026-11-12 20:20–20:45 NZ (same session)

Operator: "run all the tests and make all the changes needed." Everything below is deployed and
proven on the live box; commit `12e5593`.

### Closed
1. **Worker secret → Secret and rotated.** `CONCIERGE_INBOUND_SECRET` and `FORWARD_TO` are now
   `secret_text` in the Workers settings API. The value was rotated on both sides:
   `/opt/trendi/shared/api.env` + Worker secret + `api` recreated. Proof: signed POST with the
   **new** key → `400` (signature accepted, payload rejected); with the **old** key → `401`.
   Backup of the previous `api.env` is beside it (`api.env.bak-*`).
2. **Lost device-SMS receipts.** `api/app/outbox.py` now sweeps `awaiting_receipt`/`sending` SMS
   rows older than 15 min to `failed` ("Phone never confirmed send; reconcile before retry") and
   marks the device job `uncertain`, every 5 min — no more silent in-flight rows. First live run:
   `reconciled 10 unconfirmed SMS row(s) as failed`; `outbox` 121 sent / 10 failed, device jobs
   47 sent / 10 uncertain / 2 failed. Caddy gained `lb_try_duration 10s` + `lb_try_interval
   250ms` on both api upstreams so a deploy's Docker DNS blip is retried instead of 502'd.
   New tests `api/tests/test_outbox_reconcile.py` (they caught a real bug: asyncpg needs a
   `timedelta`, not a string — the first deploy failed live and was fixed).
3. **Host hardening.** sshd is key-only (`permitrootlogin without-password`,
   `passwordauthentication no`, validated with `sshd -t`); `ufw` active (default deny inbound,
   :22 allowed, `DEFAULT_FORWARD_POLICY=ACCEPT` so Docker forwarding survives); `fail2ban`
   active with the `sshd` jail. SSH reconnect, all public URLs and container egress verified after.

### Stale tests fixed (they were red on `main`; CI only runs on pull_request)
- `customer_authorization_test.py` — `MemoryDb` now accepts the `set_config` provenance call and
  records the audit on the INSERT.
- `customer_onboarding_integration.py` — invitation link is `/studio` (the new portal), not
  `/owner-ui`.
- `owner_customer_journey_test.cjs` — the page harness now provides `document.addEventListener`.

### Test results (final)
API **606 passed** (1 deselected `hangs_on_py312`); isolated battery **17/17** against a fresh
Postgres per suite (previously 15/17 on the same DB); node widget **9/9**; Rust social-service
**all pass**; email-auth **6/6**. Live healthcheck **44 ok / 0 warn / 0 fail**.

### Not done / still open
- **Uptime Kuma still has 0 monitors.** Left running pending the operator's decision: it is a
  self-hosted uptime dashboard that duplicates healthcheck.py + GitHub Actions here, so the
  recommendation is to remove it (or leave it stopped) rather than configure a third monitor.
- Brevo plan/IP/SMTP key, DMARC `p=reject`, scratch tenants, `admin@trendibizz.com`, token split
  — unchanged, still `GO_LIVE_HARDENING.md` §3–§6.

## Second pass — 2026-11-12 20:50 NZ ("finish what you can")

- **CI now runs on push to `main`** (was `pull_request` only — that is why three stale tests sat
  red unnoticed). `.github/workflows/concierge-isolated.yml`.
- **Uptime Kuma removed.** Stopped (`Exited (0)`); its health probe dropped from
  `healthcheck.py`, so the deep check is now **43/43**. Real monitoring is healthcheck.py +
  the GitHub Actions outside-in probe. Restore with `docker start trendi-auxiliary-kuma-1`.
- **email-auth**: removed the dead `any_pass` accumulator (two compiler warnings), rebuilt and
  redeployed; **6/6** tests.
- **OS updates**: 9 of 12 packages upgraded; 3 remain (`distro-info`, `python3-distro-info` —
  phased; `snapd`). **`/var/run/reboot-required` is set — reboot in a quiet window.** No service
  was restarted by the upgrade; all public URLs and containers verified after.
- **Stale `.lock` files** in `/opt/trendi/backups` removed (the current backup script has no
  lock logic, so they were inert).
- **API suite still 606 passed**; healthcheck 43/43; all public URLs 200.

### Still open (cannot be finished from here without a dashboard, payment, or a decision)
- `BREVO_WEBHOOK_SECRET` rotation — must change the webhook URL in Brevo at the same time or
  bounce ingestion 401s.
- `ADMIN_TOKEN` — single shared token; needs a per-operator-token decision or disabling the
  admin surface.
- DMARC `p=quarantine` → `p=reject` — needs ~a week of clean aggregate reports.
- Brevo paid plan / dedicated IP / SMTP-key rotation / IP allowlist — dashboard + billing.
- Scratch tenants and the `admin@trendibizz.com` owner — a business decision; the Cloudflare
  routing rule also needs an Email-Routing-write token the current one does not have.
- Cloudflare token split — needs API-token admin rights on the account.
- Phone DID — payment/KYC. Pukeko social OAuth — external. Offsite backups — needs a
  destination + credentials. xAI key rotation — provider dashboard.
- **Reboot** — required by the upgrades; schedule it.

## Third pass — 2026-11-12 21:05 NZ (execute everything reachable)

### Done
- **Scratch tenant `concierge-test` deleted** (`DELETE 1`; all 45 tenant FKs are `ON DELETE
  CASCADE`, so its outbox/audit/mailbox rows went with it). Pre-delete dump:
  `/opt/trendi/backups/pre-scratch-delete-20261112-075303.dump`. Four tenants remain:
  `concierge`, `trendi-oauth-staging`, `trendi-meta-review`, `pukeko-construction`.
- **Cloudflare routing rule `reply concierge-test` deleted** (HTTP 200). Six rules remain and
  **Catch-all + Concierge intake are intact**. Note: the token *does* have Email-Routing write
  (the doc said read-only) — so §5's routing-rule half was possible after all.
- **Host rebooted** to activate kernel **6.8.0-149** (host back in ~26 s). Health afterwards:
  **43/43, 0 warn, 0 fail**.

### Post-reboot regressions found and fixed (the reboot was worth doing)
1. **`asterisk-bridge-1` crash-looped**: `PermissionError: /srv/app/suppressions.py`. Cause: the
   bind-mounted `api/app` source was owned `501:staff` with `-rw-------` (an earlier `rsync -a`
   preserved the Mac umask), and the bridge runs as user `app`. Fixed with
   `chmod -R a+rX <release>/api/app` and a restart. **Deploy rule: after copying `api/app`,
   always `chmod -R a+rX` it** (same trap as `/opt/trendi/shared/studio`).
2. **`trendi-social-1` could not start**: it uses `network_mode: service:api`, so it held a stale
   netns reference to the pre-reboot api container. Recreated with
   `docker compose … up -d --force-recreate --no-deps social`.
3. `asterisk-pbx-1` (exit 128) and CRM (slow Twenty boot) recovered on their own / after start.

### Verified
All four public URLs 200 (CRM took ~3 min to migrate); api, email-auth, crm, crm-db healthy;
social, asterisk-pbx, asterisk-bridge, shell all up; healthcheck **43/43**.

### Still impossible from here (proven by API probe)
- **DNS: 403** — so DMARC `p=reject` / SPF `-all` cannot be changed with this token.
- **Token list: 403** — the Cloudflare token cannot be split (§6).
- No `BREVO_API_KEY` in `api.env` (SMTP creds only), so the Brevo webhook URL cannot be updated
  programmatically → `BREVO_WEBHOOK_SECRET` rotation still needs the Brevo dashboard.
