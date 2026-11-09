# Trendi Concierge release verification gates — 2026-11-07

**Status: NOT RELEASE AUTHORIZED.** Local implementation is not a substitute for third-party provider validation, a separate security reviewer, an approved privacy notice or a tested production restore. No live message, DNS, paid-provider, push, merge or deployment is authorized by this checklist.

## Owner security
- [x] DB-backed owner-login throttling and owner RBAC tested locally (previous handoff).
- [x] Explicit, bounded, dry-run-by-default cleanup of expired sessions, used/expired invitations and expired limiter keys; 7/7 disposable-DB assertions pass.
- [ ] An independent reviewer checks authorization/IDOR, session handling, recovery, CSRF/origin, host/proxy header trust, brute force, XSS/CSP, secret isolation, dependencies and tenant boundaries; findings remediated and retested.
- [ ] Set up authorized periodic owner-maintenance run with `DATABASE_URL` explicitly supplied; dry-run and audit before `--apply`; define retention and monitor failures. **No schedule has been activated.**
- [ ] Confirm edge proxy only accepts intended Host names, terminates HTTPS, strips untrusted forwarding headers, applies rate limits and records login abuse without storing raw secrets.

## Cloudflare inbound email
- [x] Local HMAC Worker/API bridge and verification suite (previous handoff).
- [ ] Owner approves Cloudflare account, DNS hosting and any MX updates; record existing MX and rollback. Validate domain and mailbox ownership before enabling mapping.
- [ ] Configure isolated signing secret, Worker routing, retry/oversize/replay policies and DMARC/SPF behavior; no sender authentication assumption from claimed From address.
- [ ] Live test with a specifically approved external sender and private mailbox; verify receipt, dedup, tenant isolation, dead-letter/failed delivery tracking and redacted logs. Do **not** send automatic replies.

## Telephone
- [x] Local simulated relay tests (previous handoff).
- [ ] Confirm provider, NZ number availability, billing limits, transfer destination, caller privacy notice and recording policy before purchase or calls.
- [ ] With separate call approval, test inbound NZ PSTN call, interruption, hang-up, transfer-to-human, unreachable transfer target and refusal/opt-out behavior, and capture redacted receipts.

## Product, site and legal
- [ ] Owner explicitly approves product capability matrix and revised `PRODUCT.md`; distinguish local prototype from customer-available services.
- [ ] Review CSP/connect-src/frame-src for intended site and owner portal origins only; prohibit wildcard approval without threat-model review; reconcile `DESIGN.md`.
- [ ] Business/legal reviewer signs off Privacy, Terms, consent evidence, privacy contact, subprocessors/cross-border processing, marketing permissions, data subject deletion and retention schedule; no automatic acceptance inferred.

## Operations
- [x] Isolated CI workflow staged (now includes owner-maintenance suite); disposable database restore previously passed locally.
- [ ] Obtain push/PR authorization, run GitHub Actions, resolve security findings, and record immutable run URL + result. GitHub run listing as of 2026-11-07 returned no workflows.
- [ ] Configure encrypted off-host backup, least-privileged credentials, rotation, retention and an independently verified restore into a new environment; record RPO/RTO.
- [ ] Configure monitoring and alerts (existing Uptime Kuma preferred), including HTTP/DB health, auth abuse, inbound-worker errors, queue backlog, backup freshness and alert delivery confirmation.
- [ ] Agree LLM/telephony/mail/hosting spend budgets and hard provider limits; verify alerts and hard-stop paths.
- [ ] Write and rehearse rollback from staging; verify database backward compatibility and secrets rollback.

## Authorization sequence
1. Separately approve a **controlled staging** environment and its exact domain, resources and permissible test traffic.
2. After staging evidence passes, obtain **new and separate production** authorization; do not infer it from staging approval.
3. Preserve `QA/verification/office-shots/` untracked and leave the original `/Users/jo/concierge` and production Docker services untouched until authorization.

## Maintenance invocation (only with an explicit authorized database)

```bash
cd /Users/jo/work-staging/concierge-integration
DATABASE_URL='postgresql://USER:REDACTED@HOST:5432/DB' PYTHONPATH=api /Users/jo/work-staging/venv-concierge/bin/python -m app.owner_maintenance --batch-size 500
# Apply only after confirming scope and approving cleanup:
# DATABASE_URL='...' PYTHONPATH=api /Users/jo/work-staging/venv-concierge/bin/python -m app.owner_maintenance --apply --batch-size 500
```

**Do not put actual credentials in shell history or commit them to source control.** Use your approved secret-injection mechanism instead of inline credentials in real operations.
