# Go-live hardening checklist — do these when switching to real customers

Created 2026-11-12 at the operator's request. These items are **deliberately deferred**: none of
them blocks the current single-tenant setup, and each one either needs a decision, a dashboard
step, or a quiet window. They must be closed before real customer traffic goes live.

Owner: Jo (operator). Repo: `/Users/jo/work-staging/concierge-integration`.

## 1. Worker secret: plain text → secret binding  ← the item that prompted this file
`concierge-inbound-worker` keeps `CONCIERGE_INBOUND_SECRET` as a **plain_text** binding, so anyone
with Workers read access (our API token, any dashboard viewer, the upload API) can read the HMAC
key that authenticates inbound email. It is not a leak in itself, but it is the wrong storage class
for a live system.

At go-live:
1. In Cloudflare → Workers → `concierge-inbound-worker` → Settings → Variables, change the binding
   from plain text to **Secret** (encrypted). Cloudflare keeps the existing value if you use
   "Encrypt" on the existing value; otherwise set it to the current value from
   `/opt/trendi/shared/api.env` (`INBOUND_CLOUDFLARE_SECRET`) — the two must match or every inbound
   email returns 401.
2. Alternative: rotate at the same time (see §2) and set both sides together.
3. Verify: send a real email to a tenant reply address and confirm it becomes a draft (any 401 in
   `docker logs trendi-api-1 | grep inbound/cloudflare` means the secrets diverged).

## 2. Rotate the secrets that were handled in chat/session logs
These were pasted, printed, or partially printed during setup and must be rotated before real
customer data flows:
- `BREVO_WEBHOOK_SECRET` — printed in full; the webhook URL embeds it. Rotate in `api.env`, restart
  `api`, and update the URL in Brevo → Integrations → Webhooks.
- `INBOUND_CLOUDFLARE_SECRET` — partially printed; rotate together with §1 (`api.env` +
  Worker binding in the same sitting).
- `ADMIN_TOKEN` — never printed in full, but it is a single shared token; consider per-operator
  tokens or disabling the admin surface before go-live.
Rotation order that never breaks ingestion: set the new value in `api.env` → restart `api` → update
the Worker/Brevo side → send a test email → confirm a draft.

## 3. DMARC step to `p=reject`
Currently `v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.brevo.com` (live 2026-11-12). After ~a week
of clean aggregate reports — and after confirming the hosting form mail
(`include:spf.web-hosting.com`) still aligns — move to `p=reject`. Then consider tightening the apex
SPF from `~all` to `-all`.

## 4. Brevo account and sending hygiene
- The account is on the free/shared-IP plan (≈300/day). Real customer volume will outgrow it: decide
  on a paid plan and/or a dedicated IP before campaigns start.
- The SMTP key is named "Concierge" and never expires — rotate it at go-live and narrow the
  "authorized IPs" setting to the VPS address (`152.42.239.240`).
- Keep the bounce webhook (already live and proven) and the DMARC reports watched weekly.

## 5. Scratch artefacts to remove
- Tenant `concierge-test` and its mailbox `reply-5ab18b293a15d3e03ea2dd0e@trendibizz.com` exist only
  for verification; delete the tenant, the mailbox and the Cloudflare routing rule before go-live.
- `trendi-oauth-staging` / `trendi-meta-review` tenants and their reply addresses are staging
  fixtures; confirm whether they should survive.
- `admin@trendibizz.com` is bound to `trendi-oauth-staging`, which is also the catch-all intake
  path — decide the final owner of that address before real customers.

## 6. Access-token hygiene
- The scoped Cloudflare token has Workers **write** and Zone/Email-Routing read, and no DNS. For
  go-live, split it: a read-only token for health checks, and a narrow write token used only for
  deliberate deploys (or move worker deploys to CI with its own token).
- `docker inspect` prints container secrets in clear text; nothing in the health check or docs should
  paste that output.

---
## Status 2026-11-12 20:45 NZ
- **§1 DONE.** `CONCIERGE_INBOUND_SECRET` is a Cloudflare **Secret** (`secret_text`) and was
  rotated on both sides; old value now returns 401, new value 400 (accepted). `FORWARD_TO` is
  also a Secret.
- **§2 partially done.** `INBOUND_CLOUDFLARE_SECRET` rotated. `BREVO_WEBHOOK_SECRET` and
  `ADMIN_TOKEN` still to rotate. `ADMIN_TOKEN` is still a single shared token.
- §3–§6 unchanged.
