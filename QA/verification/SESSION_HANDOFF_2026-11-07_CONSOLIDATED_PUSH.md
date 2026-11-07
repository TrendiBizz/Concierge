# DEFINITIVE REPOSITORY OWNERSHIP — USER DIRECTIVE (2026-11-07)

**MANDATORY FIRST TASK NEXT SESSION: Complete the Concierge repository consolidation.**

- **`TrendiBizz/Concierge` IS THE ONE AND ONLY CANONICAL REPOSITORY FOR ALL CONCIERGE PRODUCT CODE AND DATA STRUCTURES.** Place the complete Concierge application here: backend/API, customer onboarding and owner portal, integrations, Twenty CRM bridge, queues, LiveKit/Grok calling agent, Rust social OAuth and publishing engine, tests, configuration templates, Docker Compose, documentation, backups, and deployment scripts. Keep customer production data, keys and secrets out of Git; migrate deployment/storage ownership carefully, retaining encrypted backups and private volumes.
- **`Trendiisales/trendi-site` IS THE EXISTING PUBLIC TRENDI WEBSITE, NOT THE CONCIERGE PRODUCT REPOSITORY.** Preserve its existing design, SEO, live site routes, and deployments. It should contain only website assets and the minimal Concierge embed/client integration required by the site. Move the full Concierge voice/social implementations and their supporting assets out of `trendi-site` into `Concierge`, then remove redundant copies only after build/test/deployment path parity is established.
- **No new repositories, no parallel Concierge product source-of-truth, no fragmented implementation.** `trendi-site-web` is simply another local worktree of the existing website repo, not another GitHub repository.
- **The earlier recommendation to make a new monorepo containing the website, or to leave voice/social permanently inside the website repository, was WRONG. Do not follow it.** The requested arrangement is precisely two repositories with strict ownership: Concierge product in `TrendiBizz/Concierge`; Trendi public website in `Trendiisales/trendi-site`.

## Migration execution requirements for the very next session

1. Begin at `/Users/jo/work-staging/concierge-integration` (branch `integration/concierge-v1`) and inspect both repos, linked worktrees, Docker builds, env templates, import paths, runtime mounts, service start commands, and live dependencies. Confirm current HEADs before moving code.
2. Bring the **entire existing working LiveKit/Grok voice implementation** (`/Users/jo/work-staging/trendi-site/concierge-stack/agent/` and all required supporting files) and **Rust social-service** (`/Users/jo/work-staging/trendi-site/concierge-stack/social-service/`) into organized paths within the Concierge repository. Include source, tests, scripts, Compose/build configuration, and needed documentation. Copy/migrate as owned code, not broken symlinks, and preserve functionality. Include relevant backup/restore scripts from `concierge-stack`.
3. Rewire all Concierge service build contexts, module references, API proxy routes, compose mounts, health checks, test commands and backup paths to the new canonical locations. Keep website-only pages and SEO assets in `trendi-site`.
4. Update the website to reference the independently deployed Concierge widget/API without duplicating backend, voice or social implementations. Ensure that current site SEO/design and service offering remain unchanged.
5. Run Node CRM, Python platform/owner/voice, Rust cargo tests/clippy/fmt, Docker config, browser onboarding, website preflight/SEO checks and two-tenant isolation tests. Add cross-repository boundary tests preventing Concierge source from drifting back into `trendi-site`. Do not claim a successful migration without validated parity.
6. Confirm backup paths and a safe rollback plan; preserve live services throughout. **Do not deploy, restart live services, merge to main, enable publishing/messaging or incur paid-provider changes without explicit separate approval.** Stage changes and commit independently; retain previous branches for rollback. Follow the user's approval for pushing code only as applicable.
7. Continue finishing customer OAuth, multi-tenant voice routing/recording, email/SMS permission flows, onboarding and integration tests in the canonical Concierge repository. Do not stop after moving files.

## Verified starting commits at this handoff
- Concierge: `a263807` on `integration/concierge-v1` (prior to this handoff correction)
- Trendi website repo, Concierge-stack worktree: `ceabab7` on `concierge-stack`
- Trendi website repo, website worktree: `102eaed` on `concierge-site`

`QA/verification/office-shots/` is unrelated and untracked: preserve untouched. Do not commit secrets, customer data or local runtime databases.

---

## Prior session completion and verification (retain as migration baseline)

**Concierge platform repo** `/Users/jo/work-staging/concierge-integration`:
- `7fa139d` — real Twenty filter probe (read-only), malformed email lookup fails closed.
- `7285a1c` — private CRM event receipts, tenant/event/source SHA-256 IDs, O_EXCL claims, changed-payload rejection, ambiguous outcome reconciliation, persistent ledger volume.
- `d3b7a33` — owner business profile and private channel overview.
- `5658651` — synthetic owner portal Chrome test.
- `a263807` — original consolidated handoff, now corrected by this directive.

**Currently misplaced Concierge product components in website repo** `/Users/jo/work-staging/trendi-site` branch `concierge-stack`:
- `969a0f7` — optional CRM ledger encrypted backup/restore integration.
- `ceabab7` — Rust Mastodon and LinkedIn text-only posting connectors, off-by-default. Preserve previously built OAuth integrations.
- Existing `concierge-stack/agent/` houses working LiveKit/Grok voice implementation, which must remain fully functional through relocation.

**Website worktree** `/Users/jo/work-staging/trendi-site-web` branch `concierge-site`:
- Current Trendi public design and SEO retained. Production SEO gate 21/21 PASS.
- Fresh candidate manifest at `/tmp/trendi-seo-candidate-bundle`, preflight 31/31 PASS. No deployment made.

**Tests last verified:** CRM Node 27/27, Concierge platform pytest 52/52, owner/CRM/onboarding 21/21, Chrome onboarding 11/11, LiveKit/Grok voice 54/54, Rust cargo test/fmt/clippy PASS; private bridge Compose config PASS.

## Customer functionality still requiring real-world approvals/verification

Real provider OAuth consent and app review; other major social connectors; per-customer SIP/PSTN routing and consented recording; authorized email/SMS customer grants, revocation and isolation; private CRM bridge disposable real-record and restore tests; holistic onboarding and deployment/SEO/legal verification. Keep live social publishing and customer messaging disabled. Do not mistake mocked tests for real-provider success.

## Resume in a new session

Read this handoff FIRST, then check source and active services. Execute the code migration immediately in dependency order instead of creating another handoff or proposing another repo. The user expressly requires **all Concierge implementations amalgamated into `TrendiBizz/Concierge`, with the public `Trendiisales/trendi-site` maintained separately.**

Mac zsh:
`git -C /Users/jo/work-staging/concierge-integration status -sb`
`git -C /Users/jo/work-staging/trendi-site status -sb`
`git -C /Users/jo/work-staging/trendi-site-web status -sb`
