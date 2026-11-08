# Trendi VPS migration — 8 November 2026

Production is served from the DigitalOcean VPS at `152.42.239.240` (8 GB RAM,
2 vCPUs, 160 GB disk). Website, Concierge API, social vault, Twenty CRM/server and
worker, databases, Redis, gateway and both Cloudflare connectors are running.
Public requests carry `X-Trendi-Release: 20261108-vps`.

## Preserved and verified

- Website source `3241f54`, existing Cloudflare worker/static content and public
  URLs. Concierge API source `ac509eb`: all 49 application/static file hashes match
  the native Linux production image. Twenty uses the original immutable
  multi-architecture image digest, with native amd64 images on the VPS.
- Final source writers were stopped before the last dumps. All records matched
  in all 23 Concierge and 121 Twenty tables after restoring those dumps. Original
  owner users/passwords/sessions, CRM uploads, Redis jobs and four encrypted
  social account connections were preserved. Legacy voice configuration/data are
  retained privately for recovery.
- Legacy database sequences were behind their row IDs, including owner session
  IDs. `repair-sequences.sql` advances them without moving a sequence backwards;
  new authenticated owner sessions and enquiries work after repair.
- Owner API: authenticated `/owner/me`, `/owner/crm` and
  `/owner/social/accounts` returned 200. Temporary verification sessions were
  removed afterwards. CRM returned the existing enquiry/task, and social returned
  four existing connections.
- Real AI answer through both the gateway and live browser widget confirmed USD
  $400/month, USD $4,080/year after the 15% discount, and the built-in CRM.
- A signed test message through the public ingress created a second CRM enquiry.
  The owner reply was revised and approved through the public authenticated API;
  the VPS outbox marked it sent. Gmail receipt was independently verified:
  subject `Re: Trendi VPS live migration test 2026-11-08`, received at
  `2026-11-08T09:28:46Z`, message ID `1a1ba7d499cbfc99`. Recipient was the user's
  designated test mailbox, admin@trendibizz.com.
- Brevo STARTTLS works on port 2525, avoiding DigitalOcean's blocked SMTP ports.
- Public SEO gate: **21 passed, 0 failed, 0 warnings**, including robots.txt,
  sitemap, IndexNow file, llms.txt, canonical URLs, 404s and www redirect.
- Public origin/protection checks: website, Concierge pricing, SEO and penetration
  testing pages, customer sign-in, widget, owner portal, CRM health, unauthenticated
  owner CRM and blocked private/admin paths.
- Real POST requests to the VPS website's security/site check tools returned
  structured results. Existing `trendi-psi` Google key was recovered from the
  existing project, with no new key or permissions. PageSpeed returned available
  and 100 for performance, SEO, accessibility and best practices on this run;
  these are a point-in-time measurement, not a permanent score guarantee.

## Traffic and security

Both existing tunnels have four registered VPS connections. Old Mac connectors
were stopped, and its owner connector disabled across future logins. Apex/www
CNAMEs now point to the existing main tunnel. All other zone DNS records,
including mailbox MX/SPF/DKIM/CAA, were preserved; the previous Pages release is
retained. Mac source app containers and original volumes remain for recovery.

Cloudflare Bot Fight Mode and continuous script monitoring are enabled. Managed
WAF, browser integrity checks and HTTP DDoS protection were verified active.
HTTPS redirection, 12-month HSTS and TLS 1.3 are active; minimum TLS was raised to
1.2. Search, training and agent crawler policies allow access; Bot Preference
Sync is enabled. Googlebot, Bingbot and AI search entries in the published
robots.txt remain allowed. Existing insecure-JavaScript replacement is active.
No paid Cloudflare add-on was purchased.

Only SSH listens publicly on the origin. HTTP/API ports are loopback-only; data
services and social token storage have no public published ports. Docker is
boot-enabled and production services restart unless explicitly stopped.

## Backup evidence

The existing encrypted R2 repository/password are preserved. The first VPS
snapshot uploaded successfully. A separate test then downloaded that encrypted
snapshot, verified SQLite/uploads/settings, and actually restored both PostgreSQL
databases in a disposable container with no network or production volumes:
**23 Concierge tables and 121 Twenty tables restored successfully**. Test data
and restored secret files were removed when the test finished.

Daily backup is scheduled for 03:15 Pacific/Auckland; a monthly actual restore
test runs on the first at 03:45. Runtime configuration, social vault key, both
PostgreSQL dumps, Redis, CRM uploads, website/product release and legacy voice
recovery files are included. Source files, screenshots, private migration dumps
and DNS snapshots are retained on the Mac; secrets remain uncommitted.

## Explicit remaining activation work

Automatic mailbox forwarding into the signed email ingress is not configured;
the domain still receives mail through its existing host. Phone and SMS providers
are not configured or certified live. No phone calls/texts were sent during this
migration. Social publishing remains disabled; linking and publishing permissions
are separate. These are channel activation limits, not migrated-data failures.

Operator/recovery instructions: `scripts/vps/README.md`. Do not roll back by
starting stale source writers: restore fresh VPS data first and run only one
host's public connectors at a time.
