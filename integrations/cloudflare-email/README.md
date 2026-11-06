# Cloudflare Email Routing -> Concierge (inactive, free-first)

Uses Cloudflare Email Routing and its Email Worker with the open-source
[postal-mime](https://github.com/postalsys/postal-mime) parser (MIT-0).
**No Worker has been deployed and no mailbox routing has been changed.**

1. Human operator verifies domain ownership, DNS/MX changes, mailbox consent,
   email forwarding impacts and Cloudflare account/free-tier restrictions.
2. Human operator privately registers each mailbox against the correct tenant via
   the operator-only POST /admin/tenants/{slug}/inbound-mailboxes API. Its default
   `enabled=false` prevents receipt.
3. Use a fresh random shared secret (32+ characters) in the API
   `INBOUND_CLOUDFLARE_SECRET` and Worker `CONCIERGE_INBOUND_SECRET`. Use HTTPS
   for `CONCIERGE_INGEST_URL` pointing to /api/v1/inbound/cloudflare.
   Never commit those values. Only operator with deployment authorization may
   configure secrets and routing.
4. After review and isolated tests, explicitly approve turning on
   `INBOUND_CLOUDFLARE_ENABLED=true` and enabling the registered mailbox.
5. Inbound creates a review-required draft only. It NEVER runs AI or sends.
   Sending remains separately gated by EMAIL_DRAFTS_ENABLED, SMTP and OUTBOX.

Security: request HMAC binds raw JSON and timestamp; server rejects messages
outside five minutes, mismatched signatures and unknown/disabled recipients.
Stable SHA-256 of raw message drives deduplication. The SMTP envelope sender is
UNTRUSTED; there is no claim of SPF/DKIM/DMARC authentication. The owner must
verify sender claims and compose an approved response. Attachments are ignored.
Do not route mail on domains still served by another active mailbox without
reviewing MX/DNS impacts. Provider retries on API rejection may occur.
