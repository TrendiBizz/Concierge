# Email pipeline assessment — 2026-11-12

Scope: the whole inbound and outbound email path for Concierge, assessed live at
2026-11-12 19:05 NZ (06:05 UTC). Live: `https://chat.trendibizz.com`, owner portal
`https://concierge.trendibizz.com/studio/`, VPS `152.42.239.240`. Repo state `d706a25` + the
changes in this session (see "Fixed today").

Evidence base: the deployed api/DB on the VPS, DNS, the live Studio bundle, the health-check
report, and a code read of `api/app/*` and `services/email-auth/src/main.rs`. Everything below
was checked against the running system, not inferred from earlier docs.

## 1. What is working, verified today

| Area | Evidence |
|---|---|
| 5 tenants, chain readiness | `GET /admin/inbound-readiness` → all five `ok: true`, `blocked: []` |
| Consent gate fails closed | refusal path `api/app/cloudflare_inbound.py:115-129`; audit row written before the 403 |
| DKIM/SPF/DMARC sidecar | `verified_by='email-auth'`, `aligned=yes` on the three newest drafts |
| Risk scoring after the size fix | drafts 25/26/27 (17:44–17:58 NZ) → `risk=low`, flags empty; pre-fix drafts stay `high` |
| Refusal audit | `inbound_audit` row at 18:11:45 NZ, `action=inbound_rejected`, reason `email_read_not_authorized` |
| Monitoring | `healthcheck.sh`: 42 ok / 0 warn / 0 fail (19:03 NZ); alert mail delivered to the owner at 18:26 |
| Studio Permissions screen | `web/portal/src/App.tsx:130`; deployed chunk `assets/Permissions-BG_AQltX.js` → 200 |

Note on the 18:26 alert mail: it was **not** a false alarm. During the guard test the tenant
`concierge-test` had consent revoked, a message was refused at 18:11:45, and consent was restored
at 18:12:42. The alert is exactly the behaviour that was built. (One wrinkle: the revoke/restore
were direct DB writes, so the authorization audit table shows no revoke and no 18:12:42 grant —
see 3.7.)

## 2. Fixed today (this session)

1. **Bounces no longer count as refused customer mail.** `scripts/vps/healthcheck.py`
   `check_inbound` now excludes `bounces-%`, `mailer-daemon@%`, `postmaster@%` senders from the
   `inbound:rejections` count. Deployed and run: 42 ok / 0 fail, with the same refusal still
   present in `inbound_audit` (audited, just not alarmed). Before: the check was red for an hour
   after any bounce.
2. **Outside-in monitor rescued from the dead session.** `.github/workflows/uptime.yml`
   (6 public URLs every 20 min, opens a labelled issue on failure) was written by the session that
   died and had never been committed — `scripts/commit-checkpoint.py` refuses untracked paths
   outside its allowlist. `.github/` added to `UNTRACKED_ALLOWED_PREFIXES`; workflow committed.
3. **n8n removed.** `trendi-auxiliary-n8n-1` and `trendi-auxiliary-n8n-db-1` had been exited since
   2026-11-09 with no port bindings; containers and image removed. Uptime Kuma is the one that runs.

## 3. Open issues, worst first

### 3.1 BLOCKER — there is no bounce handling at all
No DSN/MIME `multipart/report` parsing, no Brevo webhook, no VERP, no suppression list anywhere in
the repo (`grep` for bounce/suppression finds only two comments: `cloudflare_inbound.py:135`,
`inbound_policy.py:3`). `outbox.py:204` marks a row `sent` when the SMTP server accepts it, so a
later Deferred/Blocked/Hard-bounce is invisible.

Consequence: a dead address is retried forever, reputation erodes, and the DSN itself arrives at
`admin@trendibizz.com` (the global `SMTP_FROM`) where it is treated as ordinary inbound mail — a
draft that pollutes the CRM, or a 403. There is no suppression table and no way to mark an address
bad. This is the single biggest gap between "we monitor email" and "email is operationally safe".

### 3.2 HIGH — an unaligned DKIM pass is misreported as "DMARC failed"
`services/email-auth/src/main.rs:110-128` returns `dmarc="fail"` whenever a signature passes but
its `d=` domain is not aligned with From — even though the domain may publish no DMARC record at
all. `api/app/email_risk.py:63-67` then tests `dmarc == "fail"` first and forces `high` +
`dmarc_fail`, so the `dkim_unaligned → medium` branch at `:71-75` is unreachable whenever any
signature passes.

Consequence: forwarded mail and mailing-list mail — ordinary, legitimate traffic — is quarantined
as if spoofed, with a flag that is factually wrong. The unit test only feeds a synthetic
`dmarc="none"` (`api/tests/test_email_risk.py:81-88`), so it asserts a state the sidecar cannot
emit. This contradicts the claim in `INBOUND_EMAIL_SECURITY_2026-11-11.md`.

Fix: return `dmarc="none"` for unaligned-but-unpolicied domains (or a distinct
`dmarc="unaligned"`), and let `dkim_unaligned → medium` do the work.

### 3.3 HIGH — customer-facing replies have no Reply-To
Only `OWNER_KINDS` (`outbox.py:16` — literally `{"owner_alert"}`) get the tenant reply address as
`Reply-To` (`outbox.py:185-186`). `email_secretary_reply` — the auto-reply a customer actually
receives — goes out from `admin@trendibizz.com` with no `Reply-To`.

Consequence: when a customer answers that mail it lands in `admin@`, not at
`reply-<token>@trendibizz.com`. The inbound chain, tenant attribution and consent check are all
bypassed, and the conversation is lost to the CRM. The whole `reply-<token>` design only works if
every customer-visible message carries it.

### 3.4 MEDIUM — blocked senders are dropped silently
`cloudflare_inbound.py:134-136` returns `{"accepted": True, "dropped": "blocked"}` with no audit
row, so the one action that silently discards a customer message leaves no trace. The same code
path deliberately avoids a bounce, which is right; it should still write `inbound_audit`.

### 3.5 MEDIUM — refusals are a count, not a list
`inbound_audit` has no read endpoint (`grep inbound_audit api/app/main.py` → nothing). Studio shows
only "N message(s) refused" (`Permissions.tsx:133-136`); sender, subject and reason are visible
only via SQL. If a real customer mail is refused, nobody can see who or what without a shell.

### 3.6 MEDIUM — consent can only be granted by impersonating the owner
`record_authorization` is owner-role only (`main.py:2041-2049`); there is no operator path. In
practice consent is granted by logging in as a tenant owner, so `tenant_channel_authorization_audit`
attributes it to a synthetic owner. For a consent record that is the thing a customer may later be
asked to prove, "the operator clicked it" is the wrong attribution. It needs either real owner
self-serve or an explicit operator-grant endpoint with its own audit actor.

### 3.7 MEDIUM — the authorization audit is not authoritative
Today's guard test revoked and restored consent with direct DB writes, so the audit table shows
neither. The table is only written by `record_authorization` (`channel_authorization.py:32-50`).
Any out-of-band change — including the one used to prove the guard works — is invisible. Either
enforce "consent changes only through the API", or add a DB trigger.

### 3.8 MEDIUM — rate limits are late, mistimed and leak
Per-tenant limit is 60/h but is described as per-mailbox (`cloudflare_inbound.py:151-155` counts
`email_drafts` for the tenant). Both limits are evaluated **after** the sidecar, Rspamd and ClamAV
work (`:141-170`), so a flood still costs full verification. An allow-listed sender's
`rate_limited` verdict is downgraded from high to medium (`:171-173`), which defeats quarantine.

### 3.9 LOW
- `reply_address.ensure` ignores the `ON CONFLICT` result (`reply_address.py:44-51`): a collision
  silently no-ops and the tenant keeps no usable address.
- The Worker scrapes `Authentication-Results`/DKIM hints with a regex over the whole raw message
  (`cloudflare-email-worker.js:14-30`), so quoted content can set hints. Hints can only raise risk,
  so the blast radius is small.
- `INBOUND_EMAIL_SECURITY_2026-11-11.md` still says the payload cap is 30 KB; the code is
  `MAX_BYTES = 200_000` (`email_risk.py`) with an 800 KB API body cap
  (`cloudflare_inbound.py:22`).

## 4. DNS / authentication posture

- `trendibizz.com` SPF: `v=spf1 +a +mx +ip4:63.250.38.99 +ip4:67.223.118.42 include:spf.web-hosting.com include:_spf.mx.cloudflare.net ~all` — `~all`, not `-all`.
- DMARC: `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` — reporting only, no enforcement.
- Sending subdomain: `send.trendibizz.com` is a CNAME to
  `send-trendibizz-com.brand.brevosend.com`, SPF `v=spf1 include:spf.brevo.com -all`, MX
  `return-path.mx.brevosend.com`.
- **No DKIM TXT record found** on `trendibizz.com` or `send.trendibizz.com` at any common selector
  (`brevo`, `mail`, `default`, `dkim`, `send`, `k1`, `s1`–`s3`). Either Brevo signs under its own
  `d=` domain, or DKIM is genuinely missing. Worth confirming in the Brevo dashboard — with
  `p=none` and no aligned DKIM, authentication rests on SPF alone, which forwarding breaks
  (and that is exactly the case 3.2 misclassifies).

## 5. Doc drift found while assessing

- `HANDOFF_CURRENT_2026-11-11.md` says the Studio SPA has no Permissions screen — it does, and it
  is deployed (`App.tsx:130`, chunk 200).
- Same doc says a rejected 403 is visible only in `docker logs` — now partially fixed by
  `inbound_audit` + the Permissions count, but see 3.5 for what is still missing.
- `INBOUND_EMAIL_SECURITY_2026-11-11.md` "Fix" section claims unaligned DKIM → medium; the code
  cannot produce that state (3.2).

## 6. Recommended order

1. Bounce handling + suppression list (3.1) — design first: where the bounce webhook lands, and
   what "suppressed" means for outbox retries.
2. `Reply-To` on every customer-visible message (3.3) — small diff, big functional win.
3. DMARC misclassification (3.2) — Rust change + test that feeds the sidecar's real output.
4. Audit gaps: blocked-sender rows (3.4) and a read endpoint for `inbound_audit` (3.5).
5. Consent attribution and audit authority (3.6, 3.7).
6. Rate-limit placement and the allow-list downgrade (3.8).
