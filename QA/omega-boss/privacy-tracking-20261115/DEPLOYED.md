# privacy-tracking-20261115: deployed 15 Nov 2026 17:18 NZDT (Omega Boss)
- Adds "Email delivery and link tracking" to /privacy and tightens the Cloudflare Web Analytics line. Wording checked against api/app/engagement.py (TRACKED_KINDS owner_alert, campaign, email_secretary_reply; first click stores time, link, IP, user agent), outbox.py and the /webhooks/brevo handler.
- Base guard 5e14ff93 matched; staged fa6d1c6a written. deploy-on-vps.sh sha256 cf2f2c99...438d. Backup + ROLLBACK: /opt/trendi/backups/privacy-tracking-20261115.
- seo-gate.sh (no skip flags) PASS=21 FAIL=0 WARN=0. Cloudflare purged /privacy, /privacy.html, /privacy/, www/privacy.
- Repo website/privacy.html was stale (still had the "operated from worldwide" bulk-rewrite bug); it now matches the live bytes.
- Cloudflare Web Analytics was already on (site created 2026-10-24, auto-install). Beacon loads under the existing CSP; /cdn-cgi/rum POST 204; no console CSP errors. No CSP change.
