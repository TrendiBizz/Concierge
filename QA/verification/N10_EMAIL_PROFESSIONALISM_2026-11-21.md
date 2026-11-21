# N10 Email professionalism (2026-11-21)

Cause: one global From; thread key `sha256(sender)` merged unrelated subjects; replies had no
In-Reply-To/References; inbound attachments were flagged but never listed.

Fix (`api/app/email_threading.py`, wired in inbound_email, cloudflare_inbound, email_drafts, outbox, mailer):
- Thread key = References root / In-Reply-To, else sender + normalised subject.
- Inbound Message-ID/References and attachment metadata (name, type, size) stored on the draft; the owner
  sees an attachment line in the enquiry. Bytes are NOT stored.
- Approved replies carry In-Reply-To and References.
- Per-tenant `send_from_address` used as visible From only when `send_from_verified` (operator sets it via
  the admin tenant update; a changed address resets verification). Envelope sender stays the SMTP account.

Proof: tests/test_email_threading.py (9); mutation (drop In-Reply-To) failed 2 tests, restored; full suite 1643 passed.

Not done: automatic DNS (SPF/DKIM/DMARC) verification and per-tenant DKIM keys; attachment byte storage;
Gmail/M365 send-as. Needs: an SMTP provider that signs for tenant domains, and a DNS library/provider API.
