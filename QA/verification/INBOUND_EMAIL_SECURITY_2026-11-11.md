# Inbound email security — 2026-11-11

## Principle

Inbound email is **data, never instruction**. A malicious sender can at most
create a quarantined record for a human to read. It cannot make Concierge run a
model, call a tool, book, send, pay, or change its rules.

## Threat model

| Threat | Control |
|---|---|
| Spoofed sender | Authentication hints from headers (SPF/DKIM/DMARC) are passed through and shown; all senders are treated as unverified because Cloudflare Email Routing does not itself authenticate mail. |
| Phishing / malicious links | Text-only storage (HTML stripped by the Worker); links are never fetched, rendered, or followed; they are listed as inert text for review; many links or local/private-IP links raise the risk. |
| Prompt injection ("ignore instructions, book a meeting") | No model call on ingestion. The draft is a fixed "REVIEW REQUIRED" placeholder; the enquirer's text is stored as untrusted content only. |
| Malware attachments | Attachments are never fetched or stored; the message is flagged "attachments_not_stored". |
| Flood / spam | HMAC-authenticated Worker, 5-minute timestamp window, 200 KB raw-message cap (the Worker forwards `raw_b64` only up to 200,000 bytes; the API body cap is 800 KB), per-mailbox 60/hour cap counted per recipient and checked *before* DKIM/Rspamd/ClamAV (excess rejected); per-sender 10/hour cap (excess quarantined, not lost). |
| Duplicate/replay | Signed payload + timestamp + unique `(tenant, source_id)` dedupe. |
| Cross-tenant delivery | Recipient resolved only through `inbound_mailboxes`; unknown mailbox → 404; `email_read` authorisation required. |
| Auto-reply abuse | Auto-reply is opt-in and is skipped for high-risk mail; when enabled it drafts only (no tools, no sending). |
| Reply loops | The Worker forwards the original to the owner's inbox after storing; replies go only through the approved outbound queue. |

## Boundary (already in place)

- HMAC-SHA256 signature over `timestamp.body`, compared with `hmac.compare_digest`.
- Exact required fields; unknown fields rejected.
- Body size, NUL, message-id, recipient, subject limits.
- Mailbox mapping + `email_read` permission.
- `email_drafts` unique index for idempotency.
- No model, no tools, no auto-send on ingestion.

## Added 2026-11-11

- `email_risk.assess()`: pure classifier returning `low|medium|high` plus flags
  (`unverified_sender`, `dmarc_fail`, `auth_fail`, `reply_to_mismatch`,
  `attachments_not_stored`, `oversized`, `many_links`, `local_link`,
  `sender_rate_limited`).
- **Quarantine**: `high` risk → `status='quarantined'`; the owner sees the risk
  and flags and must **Release for review** before editing or approving.
- **Rate limits**: 60/mailbox/hour → 429; 10/sender/hour → quarantine.
- **Worker**: passes `auth` hints, `reply_to`, `size`, `has_attachments`; still
  never sends attachments.
- **Portal**: risk label + flags on each draft, quarantine notice and release
  action.
- Tests: `api/tests/test_email_risk.py` (8 cases); full suite 523 passed.

## Residual risk (accepted, documented)

- Cloudflare Email Routing does not perform DMARC/DKIM verification, so the
  authentication hints are advisory. Sender identity is **not trusted**; the
  owner decides.
- No antivirus/URL-reputation scanning. Links are inert text and attachments are
  discarded.
- Quarantine is a speed bump, not a sandbox: a human can release a bad message.
  The reply still requires an authenticated owner/editor and an outbound queue.
- The Worker forwards the original to the owner's Gmail, so the owner's inbox is
  the mail system of record for deliverability.

## What "no maliciousness" means

There is no path from an email to an automated side effect. The worst case is a
quarantined row with attacker text, which a human sees and discards or releases.

## Phase 1 implemented — 2026-11-11 12:45

- **Sender policy per tenant** (`inbound_sender_rules`): exact address or `@domain`,
  `allow`/`block`. Block wins. A blocked sender is accepted and **dropped without a
  bounce** (no backscatter to a spoofed address); an allowed sender has high-risk
  quarantine capped at `medium` but still gets full flags and human review.
- **Audit trail** (`inbound_audit`): `received`, `released`, `approved`,
  `discarded`, `rule_added`, `rule_removed`, with actor and timestamp.
- **Two-person release**: quarantine release is **owner-only**; editors can edit
  only after release, and approval is owner-only.
- **Portal**: allowed/blocked sender UI; quarantined drafts show risk, flags and a
  release action; links in the untrusted body are **defanged** (`hxxp(s)://`) and
  never rendered as clickable.
- **Verified live**: blocked probe returned `{"accepted":true,"dropped":"blocked"}`
  with no CRM row; allowed probe with `dmarc=fail` + private-IP link produced
  `risk=medium, status=draft`; receipt recorded in the audit table.
- **Tests**: 527 passed (4 new policy tests).
- **Not done / next**: Rspamd + ClamAV content scanning (optional, VPS-side);
  moving inbound to a provider that authenticates SPF/DKIM/DMARC (Phase 2).

## Rust email-auth sidecar — 2026-11-11 13:00

- New Rust service `services/email-auth` (mail-auth 0.15, rust-crypto + hickory DNS)
  verifies DKIM signatures of the **raw** message and applies DMARC alignment
  against the `From` domain. Endpoint: `POST /verify {raw_b64}` -> `{dkim,
  dmarc, from, signatures}`; `GET /healthz`.
- The Cloudflare Worker now sends the raw message (base64, capped at 200 KB)
  alongside the text; the API calls the sidecar at `EMAIL_AUTH_URL`
  (`http://email-auth:8090/verify`) with a 3-second timeout and merges the
  verified verdict over the untrusted header hints. Failures fall back; mail is
  never blocked by the sidecar.
- Verified locally against a DKIM-signed message for `trendibizz.com`
  (selector `conciergetest`, TXT published in Cloudflare): `dkim=pass`,
  `dmarc=pass`, `from=test@trendibizz.com`; an unsigned message returned
  `dkim=none`. `dkimpy` verified the same message independently.
- Built and deployed as `trendi-email-auth:vps` in compose; API image rebuilt
  with `email_auth.py`; tests 529 passed.

### Verified verdicts now gate risk

- Only `verified_by=email-auth` (the sidecar) may lower risk. Header hints alone
  stay `medium` (`unverified_sender`); a hint of `dmarc=fail` still quarantines.
- End-to-end signed probe (raw message + deliberately failing header hints)
  returned `risk=low, status=draft` with `{spf:fail, dkim:pass, dmarc:pass,
  verified_by:email-auth}`; the earlier draft (before this rule) was `medium`.
- Tests: 531 passed. Test draft/lead rows and the temporary DKIM TXT record were
  removed after verification.

## Rspamd + ClamAV content scanning — 2026-11-11 13:05

- Containers added to compose: `rspamd/rspamd` (internal 11333) and
  `clamav/clamav:stable` (internal 3310, 1.8 GB limit, healthcheck). Both are
  reachable only on the compose network.
- `api/app/email_scan.py` posts the raw message to Rspamd `/checkv2` for a spam
  score and streams it to ClamAV `INSTREAM` for antivirus. Best effort: any
  scanner failure is ignored and never blocks or hides mail.
- Risk floors: virus -> high; spam score >= 6 -> high; >= 4 -> medium.
  (Minimal synthetic messages score ~3, so 4 avoids false positives.)
- Verified live: a DKIM-signed clean message returned `risk=low, status=draft`
  (spam 3.1, ClamAV clean); an EICAR message returned `risk=high,
  status=quarantined` with `virus` + `spam_high`. Tests: 535 passed.
- Operational note: the Rust sidecar caches negative DNS answers for up to an
  hour; restart `trendi-email-auth-1` after publishing a DKIM record. Test rows
  and the temporary DKIM TXT record were removed.

## Speed work — 2026-11-11 13:20

Measured on the live stack (grok-4.7; LLM latency varies run to run):

| Change | Before | After |
|---|---|---|
| Chat reply (full JSON) | 7.80 s, 5.08 s | 6.40 s, 3.85 s |
| Chat first token (stream) | n/a (waited for full) | 7.50, 2.37, 4.67, 3.08, 3.52 s (avg 4.2 s vs 5.8 s full) |
| Repeated retrieval | 21.9 ms | **0.0 ms** (TTL cache hit) |
| Static asset headers | none | `public, max-age=2592000, immutable` (Cloudflare purged) |

- `POST /api/v1/chat/stream` (SSE) + widget reader; events `token`, `replace`
  (quote guard correction), `done`. Gateway routes `/api/v1/chat/stream`.
- `rag.retrieve` TTL cache (300 s, 512 entries); repeated questions skip the
  embedding + vector query.
- Read-only tools (`search_knowledge`, `check_availability`,
  `get_booking_link`) run concurrently; mutating tools stay ordered. Prompt now
  asks the model to batch lookups. Test: two 100 ms tools finish in <180 ms.
- Indexes: added `leads_conversation_idx` and
  `conversations_tenant_started_idx`; confirmed `chunks` HNSW,
  `messages_conv_idx`, `leads_tenant_idx` already existed.
- Caddy caches `/brand/*`, `/fonts/*`, `/assets/*`, `/images/*` for 30 days.
- 538 tests pass.
- Note: grok-4.7 has a silent reasoning phase before its first token, which is
  now the floor on perceived latency. A non-reasoning model or lower reasoning
  effort would move it further.
- Perf chat runs triggered owner alerts (SMS+email). Outbox and
  `device_sms_jobs` rows were removed; SMS already delivered to the paired phone.

## Sender-verification bug fixed — 2026-11-12

Reported symptom: an owner reply was labelled `unverified_sender` (medium) although its
headers carried `dkim=pass`.

Cause: the classifier only consulted the `dmarc` label from the Rust sidecar. Two genuine
paths produced the misleading label:

1. **Verified but no DMARC record.** The sidecar returned `dkim=pass` with `dmarc=none`
   (the sender's domain publishes no DMARC record — normal for small-business mail).
   The `dmarc` label fell through to the `else` branch, which appended
   `unverified_sender` even though the signature passed and aligned.
2. **Sidecar did not run.** If `EMAIL_AUTH_URL` is unset, the sidecar times out, or the
   raw message is over 200 KB, `email_auth.verify()` returns `None` and ingestion falls
   back to header hints — which are advisory-only and therefore always medium. Nothing
   in the stored record said *why* verification was missing, so it read as a spoof
   signal.

Fix:
- sidecar: `/verify` now returns `aligned` (a passing signature whose `d=` domain is the
  From domain or a parent of it). The verdict computation is a pure, unit-tested function
  (`verdict()` in `services/email-auth/src/main.rs`, 6 tests).
- `email_auth.merge()` carries `aligned` into the stored auth record.
- `email_risk.assess()`: verified + (`dmarc=pass` or aligned) → **low**; verified but
  unaligned `dkim=pass` → medium with the accurate `dkim_unaligned`; sidecar failure →
  medium with `verification_unavailable` (never a bare `unverified_sender`).
- Behaviour kept: header hints alone still cannot lower risk, and a real `dmarc=fail`
  still quarantines at high.
- Tests: 6 Rust verdict tests, 4 new Python cases (20 pass in the email modules); full
  suite 558 → 563.

Still to do on the deployed stack: confirm `EMAIL_AUTH_URL` is set for the `api` service
and that the deployed Worker sends `raw_b64` (the repo copy at
`QA/verification/cloudflare-email-worker.js` does; the deployed copy is edited in the
Cloudflare dashboard and is not version-controlled here). The repo's `scripts/vps/compose.yml`
has no `email-auth` service at all, so the deployed compose has drifted from the repo —
reconcile it when next on the VPS.
