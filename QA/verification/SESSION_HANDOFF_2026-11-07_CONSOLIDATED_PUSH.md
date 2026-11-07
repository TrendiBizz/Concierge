# Trendi Concierge consolidated session handoff — 2026-11-07

## Repository map (IMPORTANT)
There are TWO GitHub repositories, not three:
1. `git@github.com:TrendiBizz/Concierge.git` — worktree `/Users/jo/work-staging/concierge-integration`, branch `integration/concierge-v1`. Contains platform API, owner portal, CRM Twenty bridge, customer auth and workflows.
2. `git@github.com:Trendiisales/trendi-site.git` — worktree `/Users/jo/work-staging/trendi-site`, branch `concierge-stack`. Contains LiveKit/Grok calling and Rust social-service, alongside the overall site repository.
3. `/Users/jo/work-staging/trendi-site-web` is a SECOND WORKTREE of the **same** `trendi-site` repository on branch `concierge-site`, with public web design and SEO. NOT a third remote repository.

The user wants one simpler repo eventually. Do not merge or move directories without a deliberate reviewed consolidation strategy. A possible target is one repo with /website, /platform, /voice and /social, retaining deploy boundaries.

## Completed work in this conversation
Concierge branch:
- `7fa139d` — Read-only real Twenty email+NZ phone filter checks (HTTP 200 with synthetic non-matching IDs), fail-closed email result validation.
- `7285a1c` — Durable event receipts in optional private Twenty bridge, stable tenant/event/source SHA-256 ID, O_EXCL claim, replay detection, changed-payload protection, ambiguous responses quarantined, Docker persistent ledger volume. Not a cross-system exactly-once guarantee.
- `d3b7a33` — Business owner onboarding profile (greeting, notification email, timezone), tenant-scoped channel overview, owner-only updates.
- `5658651` — Isolated Chrome browser test for owner portal setup and viewer restrictions.

Trendi-site / concierge-stack branch:
- `969a0f7` — Include optional private CRM event ledger in encrypted backup + isolated restore validation.
- `ceabab7` — Rust text-only Mastodon and LinkedIn publishing adapters, official API contracts, independent per-provider publishing off-by-default flags, deterministic event key. Existing Bluesky path retained, no real publishing enabled.
- Preserve prior LinkedIn/Mastodon OAuth and social account separation.

Site / concierge-site branch:
- Existing site design maintained; SEO public gate passed 21/21 checks.
- Candidate deploy manifest generated under `/tmp/trendi-seo-candidate-bundle` rather than changing known-good deployment. Preflight against fresh manifest passed 31/31. No deploy or DNS change made.

## Verification
- CRM Node tests 27/27 PASS
- Platform pytest 52/52 PASS
- Owner/onboarding/CRM integration unittest 21/21 PASS
- Isolated Chrome owner portal 11/11 PASS
- LiveKit/Grok voice unit suite 54/54 PASS
- Rust social cargo test, cargo fmt --check, cargo clippy --locked --all-targets -- -D warnings PASS
- Docker compose private bridge overlay config --quiet PASS
- No activation of social posts, live SMS/email, public onboarding or production deployment.

## Next implementation priorities
1. Genuine provider OAuth/approval flows: tenant-bound Mastodon/LinkedIn external consenting test accounts, missing major network APIs and their developer permissions.
2. Per-customer LiveKit SIP/PSTN routing and consented recordings; current LiveKit/Grok call agent must remain intact. Existing Twilio relay adapter is separate and unverified for customer production.
3. Customer email/SMS provider-specific permissions, audited revocation, tenant isolation and live provider end-to-end validation.
4. Finish business onboarding guided channel connection UI and service readiness verification; test two synthetic tenants end-to-end.
5. Private CRM overlay and backups: approval, real disposable CRM create+note/replay/restore tests in staging, no production records, no false exactly-once claim.
6. Website/SEO, pricing and legal release verification followed by separately approved production rollout.

## Safety constraints
- Preserve running LiveKit/Grok, Twenty CRM, site and Docker services.
- Never turn on live sending, social publishing, customer onboarding, deploy/merge, or incur provider charges without separate approval.
- `QA/verification/office-shots/` is untracked and unrelated: DO NOT add, delete or modify it.
- Do not expose secrets in logs, handoff or commits.
- User specifically requested push of all verified CODE branches and this consolidated handoff in this turn, but not merging or deployment.

## Resume commands (Mac zsh)
`git -C /Users/jo/work-staging/concierge-integration status -sb`
`git -C /Users/jo/work-staging/trendi-site status -sb`
`git -C /Users/jo/work-staging/trendi-site-web status -sb`

Handoff should be reviewed against the final pushed commit IDs recorded in the session response.
