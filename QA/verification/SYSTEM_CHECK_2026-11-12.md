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
