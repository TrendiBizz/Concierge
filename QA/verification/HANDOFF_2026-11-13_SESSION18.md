# Handoff — 2026-11-13 ~10:40 NZ (session eighteen)

Where this file and `QA/verification/HANDOFF_CURRENT_2026-11-11.md` disagree, the evidence in the
repo doc wins, **except** for the corrections in §6 below, which supersede it.

---

## 1. One-paragraph state

The platform is healthy at the control-plane level (production healthcheck **0 warn / 0 fail**,
API suite **735 passed**, Hero **Registered**, 19 containers up). This session **hardened the host**
and **made owner alerts resilient** (both deployed and pushed, commit `5c95f63` on `origin/main`).
It did **not** build the onboarding flow, did **not** move the phone number to the real customer,
and could **not** place a call. **No real customer call has ever completed** (3 attempts on 12 Nov,
all `failed`/`disconnected`, cause still unknown).

## 2. Project and access (unchanged)

- Repo: `/Users/jo/work-staging/concierge-integration`, branch `main`. The
  `com.trendibizz.concierge-checkpoint` launchd agent commits every 5 min and pushes only when it
  commits. Working tree was clean and equal to `origin/main` at `5c95f63`.
- Live: `https://chat.trendibizz.com` (tenant demo `/demo/pukeko-construction`), owner portal
  `https://concierge.trendibizz.com/studio/`. Telephony entry: **+64 9 243 1347** (Hero).
- VPS `152.42.239.240`, release dir `/opt/trendi/releases/20261108-vps/product` (**not** a git
  checkout). SSH uses the repo-local key:
  `ssh -o BatchMode=yes -o IdentitiesOnly=yes -i /Users/jo/work-staging/concierge-integration/Concierge root@152.42.239.240`
- **Deploy procedure used and verified this session** (copy files, then build only `api`):
  ```
  scp <files> root@152.42.239.240:/opt/trendi/releases/20261108-vps/product/api/app/
  cd /opt/trendi/releases/20261108-vps/product/scripts/vps
  docker compose -f compose.yml --env-file /opt/trendi/shared/compose.env \
      --profile crm --profile public up -d --build --no-deps api
  ```
  **Never `--remove-orphans`** (clamav, rspamd, shell are orphans; it would remove the mail filter).
  **Never recreate the PBX without `compose.public.yml`.** After rsyncing the portal run
  `chmod -R a+rX` or `/studio/` returns 500.
- Remote Desktop Commander quirks (Mac.hub): calls return after 3 s, so run long work in the
  background writing to a file, then read the file. A harmless `getcwd` shell-init error prints on
  every call. Device id `94c529fd-3d2c-4396-a68d-cc86d0d2fb74`.
- Local tests (no pytest on the system Pythons). A throwaway venv exists at
  `~/audit-20261113/venv` (python3.13, both requirements files installed). Run from `api/`:
  `cd api && ~/audit-20261113/venv/bin/python -m pytest tests -q -p no:cacheprovider`
  (expects **735 passed**). If that folder is deleted, recreate:
  `python3.13 -m venv V && V/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt`.

## 3. What this session changed (all verified)

### 3a. Host hardening — `scripts/vps/harden_host.sh` (idempotent, re-runnable)
| Change | Evidence |
|---|---|
| UDP 5060 restricted to `103.212.52.0/24` via `DOCKER-USER` → `TRENDI-SIP` chain, made persistent by `trendi-sip-firewall.service` (`/usr/local/sbin/trendi-sip-firewall.sh`) | ~2,900 scanner packets dropped in the first minute; forced re-registration succeeded; scanner REGISTER lines in the log fell to 0 |
| RTP `10000–10099/udp` **deliberately left open** | A media gateway on another address must not cause one-way audio |
| IPv6 udp 5060 and 10000–10099 dropped (Hero is IPv4-only) | in the script |
| PBX container log was **2.6 GB**; truncated, logrotate `copytruncate` (100 MB, 3 kept) and `/etc/docker/daemon.json` caps (apply on next container recreate; Docker was **not** restarted) | tail kept in the backup dir |
| sshd: `X11Forwarding no`, `MaxAuthTries 3`, `LoginGraceTime 20`, root key-only (`/etc/ssh/sshd_config.d/00-trendi-hardening.conf`, validated with `sshd -t`) | reloaded OK |
| fail2ban: sshd jail 1 h ban / 3 tries, plus `recidive` (1 week) | 2 jails active |
| 3 package updates applied (distro-info, python3-distro-info, snapd) | 0 pending |

**Rollback of the firewall:** `systemctl disable --now trendi-sip-firewall` then
`iptables -D DOCKER-USER -p udp -m conntrack --ctstate DNAT --ctorigdstport 5060 -j TRENDI-SIP`.
State backup: `/opt/trendi/backups/harden-20261112-211444/` (iptables-save, sshd, fail2ban, docker,
PBX log tail).

### 3b. Alert resilience — `api/app/channel_health.py` (new) + hook in `api/app/outbox.py`
- `escalate_failed_owner_alerts()` runs in the existing 5-minute outbox sweep. An `owner_alert` that
  ends `failed`/`held`/`suppressed` is re-queued **once** on the other channel (SMS→email,
  email→SMS), dedupe key `fb:<id>:<channel>`; fallback rows are never re-escalated (no loops);
  window 24 h, 50 rows per sweep. Voice-call alerts already queue both channels in
  `asterisk_bridge.py`, so they are covered.
- `channel_report(tenant_id)` returns `email`, `sms` (device paired/verified/last seen, offline
  after 15 min) and `voice` (recent call outcomes) status. **It is not yet exposed by any API route
  or shown in the portal** (see §5).
- 9 new tests in `api/tests/test_channel_health.py`. Deployed; the sweep ran in production at once.
  The first run re-queued a 24 h backlog of stale staging alerts; the 9 pending texts were cancelled
  by hand so they cannot flood the staging phone. The 9 matching emails stay and will fail against
  the blocked address (harmless).
- Rollback: previous API image is still on the VPS (`trendi-concierge-api:2fbda86` and the
  `before-2026111x` tags); `/opt/trendi/backups/api-20261113/outbox.py.bak` is the old `outbox.py`.

### 3c. Data change
- `tenants.notify_phone` for `pukeko-construction` set to **+6421824305** (Conrad Schiess, Managing
  Director, conrad@pukekoconstruction.co.nz — the notify email was already set to that address).
  `phone_enabled` and `sms_enabled` are **still false**; nothing changes for Pukeko's customers yet.

## 4. Root causes found (read-only investigation)

1. **SMS is sent by a physical phone device** (`sms_devices` / `device_sms_jobs`; the "own system").
   The device was last seen **2026-11-11 00:20 UTC** (silent ~45 h at audit time) and
   `inbound_verified_at` is empty. Last successful SMS: 10 Nov 03:07. Since then 15 jobs are
   `uncertain` and their outbox rows `failed: Phone never confirmed send; reconcile before retry`.
   **Decision (user): keep the phone-device approach — no carrier integration.**
2. **Email:** 70 owner-alert emails failed `blocked: due to blacklist user` plus 4 `suppressed`, all to
   the staging alert address (`admin@trendibizz.com`). Brevo has it on the block list. The server
   holds no Brevo REST key (only `BREVO_WEBHOOK_SECRET`), so it cannot be unblocked from here.
3. **Calls:** cause of the 3 failed calls is **unrecoverable from logs** — the bridge container was
   restarted at 10:26 on 12 Nov (its logs start there), the PBX logs hold no INVITE records for the
   window, and `phone_calls` rows have empty `from_number` and `session_id` and no failure reason.
   **Hypothesis, not confirmed:** the PBX only identifies Hero as `103.212.52.17/32`
   (`match=sip.hero.co.nz`); if Hero ever sends calls from another address they are rejected with no
   clear error. Hero's DNS (SRV and A) returns that single host.
4. **Dialplan catch-all:** `/etc/asterisk/extensions.conf` `[concierge-ingress-1]` sends
   `+6492431347` **and** `_.` (everything) to `business-trendi-oauth-staging`. Any new number
   silently lands on staging.

## 5. Outstanding — the full list (nothing here is optional)

### 5a. Human actions only the operator can do (do these first)
1. **Wake the SMS phone** — open the app on the paired device so it polls; confirm
   `sms_devices.last_seen` advances and `inbound_verified_at` gets set.
2. **Unblock the staging alert address in Brevo** (Transactional → Blocked contacts). Find out why it
   was blocked (hard bounce / earlier unsubscribe) before re-enabling sends.
3. **Make the real test call** to **+64 9 243 1347**: give the full enquiry including a callback
   number and an email read aloud. Expect no dead air, details read back, enquiry saved, owner alert
   fired, `phone_calls.status = completed`. **This is the only way to learn why calls failed, and it
   also proves the new SIP firewall with a real inbound call (never tested).** If it never rings, run
   `iptables -L TRENDI-SIP -v -n` on the VPS — a rising DROP count with Hero traffic means widen
   `HERO_NETS` (env var of `harden_host.sh`) or ask Hero for their full call-origin address list.
4. Then supervision on that real call: Studio → Bookings → "Happening now" → **Listen in** → answer →
   hear the caller → **Stop listening** → "Who listened" shows one closed leg. Note Listen in rings
   +64278817368 (staging) until the DID's tenant is moved.
5. Then take-over, whisper, join, and the 30 s no-answer fallback into the assistant.
6. **Send Conrad the plan-upload link** (`/upload/{token}`, created 2026-11-11, 0 uploads; sending
   never confirmed).
7. Read/decide the **11 email drafts** (8 quarantined, 3 draft).
8. Ask Hero for their **full list of call-origin (INVITE source) addresses** and whether they offer
   an SMS/voice status API.

### 5b. Phone / voice (carried from the old list, status updated)
- Move the DID to **`pukeko-construction`**: set `phone_enabled = true`, point `[concierge-ingress-1]`
  at `business-pukeko-construction` (replace the `_.` catch-all with explicit DIDs and a reject for
  unknown numbers), and send Conrad a **test alert on SMS and email and have him confirm** first.
  Do not move it before alerts are proven to reach him.
- Transfers/supervision use `managed_phone_setups.owner_number`, else `tenants.notify_phone`;
  Pukeko now has `notify_phone`, so supervision should no longer refuse — verify. No
  `managed_phone_setups` rows exist.
- Add `failure_reason` (and capture `from_number` / `session_id`) to `phone_calls`; **persist bridge
  logs across restarts** (ship to a file or set a log driver) so a failed call can be diagnosed.
- Missed-call text-back inert for Pukeko (`sms_enabled=false`) — business decision plus transport.
- `payment_instructions` unset for Pukeko, so "Get paid on an accepted quotation" reads
  `unconfigured`.
- Limitation: AudioSocket carries no caller ID (the agent asks for a callback number); transferred
  calls show the business CLI to the owner.
- Not built on purpose: multi-call supervision/queue/roster; browser listen-in (WSS/DTLS/ICE).
- Review the live-listen **disclosure copy** (customer-facing; highest of the lower items).

### 5c. Alert resilience — finish the job
- Expose `channel_health.channel_report` through an owner API route and show email/SMS/voice status
  in the portal; add it to `scripts/vps/healthcheck.sh`.
- **Operator alert when the SMS device goes silent** (today only the owner fallback exists); needs an
  operator email setting that is *not* the blocked address.
- Stop the retry storm for blocklisted addresses (70 retries happened before the audit): treat the
  provider's blacklist response as a permanent suppression, with a dead-letter state.
- Voice fallback for alerts that fail on **both** SMS and email (AMI `originate` is permitted by the
  scoped AMI user) — not built; the user asked for resilience across email, SMS **and voice**.

### 5d. Onboarding — the major remaining build (user wants it as seamless as possible)
Current state (from `QA/verification/CUSTOMER_ONBOARDING_2026-11-09.md`; code not re-read): operator
creates the business and a private invite link in the admin UI; link is single-use, expires in 24 h,
**no email is sent automatically**; owner sets a password, lands in the right workspace, follows a
checklist (business details, knowledge upload, social providers). **Gaps:** manual link sharing; 24 h
expiry; no phone/transfer-number capture; no check that alerts actually arrive before go-live;
SMS depends on a paired phone; widget install is not verified; **no real-browser QA was ever run**;
Meta app review, TikTok sandbox and LinkedIn Page management are external blockers.
Target flow (~10 minutes):
1. Invite **emailed automatically**; longer-lived or re-issuable link.
2. Password set → workspace opens.
3. Business details **prefilled from the website URL** (owner approves; no silent crawl).
4. **Alerts step with a hard gate:** owner enters mobile + email; a test SMS and test email must be
   *confirmed* before `phone_enabled` can be switched on (this would have caught the failures found
   this session). Include SMS-device pairing with a clear "keep the app open" health indicator.
5. **"Call me to test"** button (AMI originate to the owner's mobile, plays the greeting).
6. **Widget snippet** with copy button and a "verify installed" check; later WordPress/Shopify/Wix
   guides.
7. Go-live checklist with the per-channel health from §5c.
Also: real-browser and accessibility QA; a controlled real-customer consent test.

### 5e. Go-live security (`QA/verification/GO_LIVE_HARDENING.md`)
Rotate `BREVO_WEBHOOK_SECRET` (and its Brevo webhook URL together) and `ADMIN_TOKEN`; Brevo paid plan
/ dedicated IP, rotate the SMTP key and narrow authorised IPs to `152.42.239.240`; DMARC
`p=quarantine` → watch ~a week → check `include:spf.web-hosting.com` alignment → `p=reject`; delete
scratch tenants and `admin@trendibizz.com`; split the Cloudflare token; rotate the xAI key (visible
in `docker inspect`); Worker secret plain-text → Secret binding.
**New:** the AMI secret (`/etc/asterisk/manager.conf`) and the Hero SIP password (`pjsip.conf`) were
printed into this session's transcript by a grep, and sit in plain text in those mounted config
files. The operator says these are **test credentials and will be changed** — treat as a go-live
rotation, not urgent. Delete `~/audit-20261113/` (holds that output) before go-live.

### 5f. Media-server ops, external, watching (carried)
Scoped AMI user cannot run `CoreShowChannels`/`Events: on` (client uses `Status`); a Local-channel
supervision leg is two channels both marked `CONCIERGE_SPY` (a second `Hangup` logging "No such
channel" is harmless). Pukeko social accounts (per-network OAuth); live social publishing; off-site
SEO accounts; 3 phased host packages may remain. Watching: Astryx Native (Mondays 09:00 NZ, still a
placeholder), `.github/workflows/uptime.yml` red runs (GitHub was not connected, not read), bridge
log signatures (`Benign Grok cancel race` = noise; `Grok telephone session error <code>` = real;
`Caller turn went unanswered` = nudge fired). Richer internal admin console; remove the old test
phone route. Scheduled: daily GEO check 07:00 NZ; Astryx Mondays 09:00 NZ.

### 5g. Housekeeping
- Merge this file's §3–§6 into the authority doc `HANDOFF_CURRENT_2026-11-11.md` consolidated list.
- The DSH harness patch (`dsh-batch-tool-calls@1.1.2`, profile `web`) from the previous handoff is
  unrelated to Concierge and was not touched.

## 6. Corrections to earlier statements (these supersede older docs)

- **Offsite backup is working.** Encrypted restic backup to a remote repository (`backup.env`:
  `RESTIC_REPOSITORY`, S3-style keys) runs daily at 14:15 UTC; `systemctl` logged
  "Encrypted VPS backup uploaded successfully" on 12 Nov. An earlier note in this session that
  backups were local-only was wrong. Restore test runs monthly (next 30 Nov).
- The VPS has ~7.9 GB RAM and no swap despite the old droplet slug naming `1gb`.
- Healthcheck count: **43 ok** at the last handoff; this session's run reported 0 warn / 0 fail.

## 7. Verified safe / fine at audit time
Postgres and the API are not host-published (API bound to 127.0.0.1:8000); all `/opt/trendi/shared/*.env`
are `0600 root`; nothing world-writable under `/opt/trendi`; TLS certs valid to **22 Jan 2027**;
password SSH off; disk 36% (54 G of 154 G); fail2ban active.

## 7b. Added later in the same session (deployed and pushed; API suite now **748 passed**)

New code in `api/app/channel_health.py` and `api/app/main.py`, tests in `test_owner_invite_email.py`
and `test_go_live_gate.py`. Rollback: image `trendi-concierge-api:before-20261113-gate`, files in
`/opt/trendi/backups/api-20261113b/`.

- **Opt-in invitation email:** `POST /admin/tenants/{slug}/owner-invitations` accepts
  `send_email: true` (default false, so the operator can still deliver the link by hand). The link is
  single-use, 24 h, secret in the URL fragment (mail scanners cannot consume it). A failed send never
  loses the link (`emailed`/`email_error` in the response); the token is never logged.
- **`GET /owner/channel-health`** — email / SMS-device / voice status for the caller's business.
  *Not yet shown in the portal UI or in `healthcheck.sh`.*
- **Alert tests:** `POST /owner/alerts/test` (owner role) and `POST /admin/tenants/{slug}/test-alert`
  queue a labelled test alert on each configured alert channel (dedupe key `test:<tenant>:<channel>:<ts>`).
- **Go-live gate:** `PATCH /admin/tenants/{slug}` refuses `phone_enabled: true` (409,
  `alerts_not_proven`, with reasons) unless the owner's mobile **and** alert email are set **and** at
  least one owner alert was *delivered* (`status='sent'`) in the last 7 days. `?force=true` is the
  operator override. `notify_phone` is now settable through the same endpoint (it was SQL-only).
  Design note: one proven channel is enough, so Pukeko (6 real alert emails delivered, last 12 Nov)
  already passes — tighten to "both channels" if you want SMS to be mandatory.
- **Incident, fully reverted:** while verifying, a PATCH sent to production as a "safe 409 test"
  was accepted and set Pukeko `phone_enabled = true`. It was reverted to `false` within minutes
  (verified in the DB); the DID still routes to the staging tenant, so no customer call was affected.
  The tenant JSON printed by that call also exposed Pukeko's `report_token` and `calendar_token`
  (and the public widget key) in the session transcript — rotate those two tokens at go-live.
  **Lesson: verify gates with unit tests or read-only queries, never with a mutating production call.**

## 8. Next action (in order)
1. Operator: wake the SMS phone and unblock the Brevo address (§5a-1, 2).
2. Operator: make the real test call and report what happened; read bridge/PBX logs during it
   (`docker logs -f asterisk-bridge-1`, `docker exec asterisk-pbx-1 asterisk -rx "pjsip set logger on"`
   — turn it off afterwards).
3. Claude: with those results, fix whatever the call exposes, then move the DID to Pukeko behind a
   confirmed test alert to Conrad.
4. Claude: build §5c then §5d (onboarding); full file edits, run the full API suite (735
   baseline), deploy with the §2 procedure, push. (Work continued in the same session; context was
   only ~20% when this file was written.)
