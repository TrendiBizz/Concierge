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
| Flood / spam | HMAC-authenticated Worker, 5-minute timestamp window, 30 KB payload cap; per-mailbox 60/hour cap (excess rejected); per-sender 10/hour cap (excess quarantined, not lost). |
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
