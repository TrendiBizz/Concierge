# Trendi Concierge: free-first open-source decisions (2026-11-07)

A free software license does NOT make phone calls, email delivery, compute,
storage, DNS, support, legal review or cloud account usage free.

| Area | Selected | Considered | Decision and gate |
|---|---|---|---|
| Inbound email | Cloudflare Email Routing + Workers (Free tier) and postalsys/postal-mime (MIT-0) | Mailgun, Brevo, EmailEngine/self-hosted MX | Implemented locally; domain must use Cloudflare DNS, MX changes need explicit approval; routing and HMAC secret not configured |
| Owner security | Existing FastAPI + Postgres | Authentik, Keycloak, Ory | Current tenant-aware RBAC is smallest compatible path; further independent security review needed |
| Telephone | Existing guarded Twilio Conversation Relay adapter | pipecat-ai/pipecat (BSD-2), livekit/agents (Apache-2 framework), kirklandsig/AIReceptionist | Do not replace unvalidated telephony with another unvalidated stack; real numbers/PSTN and many speech APIs cost money; compare on measured NZ call performance only |
| Monitoring | Existing self-hosted louislam/uptime-kuma (MIT) | Grafana, Prometheus, Gatus | Reuse existing instance; add healthz and alert configuration only after authorized staging access |
| Backup | Existing pg_dump + restore canary; consider restic/restic (BSD-2) for encrypted off-site copies | Kopia | Local restore proof passed; does not prove production restore or offsite resilience |
| Vulnerability/secret scan | aquasecurity/trivy (open source) | gitleaks/gitleaks | Isolated GitHub CI static job drafted, not executed on GitHub; verify findings before release |
| CI | GitHub Actions (included usage subject to account and limits) | local shell-only checks | 11 separate Python test jobs, static checks and restore proof; no workflow dispatched/pushed |

Sources:
- https://developers.cloudflare.com/email-service/platform/pricing/
- https://developers.cloudflare.com/email-service/get-started/route-emails/
- https://github.com/postalsys/postal-mime
- https://github.com/pipecat-ai/pipecat
- https://github.com/livekit/agents
- https://github.com/louislam/uptime-kuma
- https://github.com/restic/restic
- https://github.com/aquasecurity/trivy
- https://docs.github.com/en/actions/concepts/billing-and-usage

## Important risk gates

1. No user-authorized public ingress, worker deployment, outbound approval, paid
   account change, telephone number purchase, live call or production modification.
2. Mail reception requires verified tenant mailbox ownership and explicit permission
   to change domain MX, which could disrupt existing email.
3. The inbound core method trusts the upstream HMAC-verified Worker, not
   the email's claims about its sender. It does not authorize sending.
4. Trivy runs only if CI is executed after explicit push/PR authorization; do not
   claim that the secret/vulnerability scan has passed now.
5. Public owner portal requires reverse-proxy policy review, robust lockout strategy
   and abuse alerting, operational session cleanup and verified key-handling.
6. Neither a disposable restore test nor healthz proves recoverability of real
   volumes. An off-host encrypted backup and production restore rehearsal remain.
7. No full legal review has been performed. Privacy/retention, consent, call notices,
   promotional messaging, subprocessors, response ownership and deletion rights
   require business and legal approval.

## Website/product reconciliation

Reviewed the separate site worktree at
/Users/jo/work-staging/trendi-site, branch concierge-offering.
Its live PRODUCT.md (reviewed 2026-10-31) describes only SEO/AI visibility.
research/PRODUCT.proposed.md adds Concierge but is explicitly UNAPPROVED.
The draft says 'AI lead scoring' is not built: the API actually implements
rule-based, configurable 0–100 scoring (see api/app/scoring.py), not
AI/model scoring. That specific wording is technically correct only if 'AI'
is emphasized; avoid saying 'lead scoring is not built'. All draft claims of
'offered today' must be checked against deployed production, not only isolated
test passes. New owner portal, email ingress and phone adapter are local-only,
so the site must not present them as live. Do not modify approved product truth,
site CSP exceptions, pricing, Terms or Privacy without separate approval.

Release approvals still needed: proposed PRODUCT.md adoption, DESIGN.md update,
CSP review for chat.trendibizz.com, domain/email routing, Privacy/Terms,
phone recording/consent, hosting, monitoring and paid model spend limits.
