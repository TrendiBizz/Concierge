# Status verification and handoff correction — 2026-11-17 (evening NZDT)

This is a read-only status pass, not a product change. It exists because the handoff and the
Hermes rollout record disagreed with the repository and with each other, and the Hermes workstream
was missing from `HANDOFF.md` entirely.

**Why this file is named `STATUS_HERMES_…` and not `HANDOFF_HERMES_…`:** `.gitignore` excludes
`QA/verification/HERMES_*` and `QA/verification/HANDOFF_HERMES_*` because this repository is public
(the Hermes design notes have never been committed). Any record beginning with those prefixes is
silently untracked. This one is deliberately outside both patterns so it can be committed; the
Hermes rollout/framework records remain local-only.

## Documentation defects found

1. **`HANDOFF.md` named the wrong HEAD, twice.** §1 and §4 said `8a16ca1`; the tree, `origin/main`
   and the commit that wrote the handoff were `be9a647`. Cause: a handoff cannot contain the hash of
   the commit that writes it, so it named the previous commit and was never corrected. Correcting it
   to `be9a647` reproduced the same trap one commit later. Fix: the handoff now names the **last
   measured code commit** (`be9a647`) and states that the handoff commits after it are docs-only;
   it no longer claims to be the tip. Future handoffs should do the same rather than hardcode a
   hash they cannot know.
2. **The Hermes rollout was not in the handoff worklist.** `QA/verification/HERMES_ROLLOUT_2026-11-17.md`
   records the gateway deployment, the per-tenant container and the 7am note, but `HANDOFF.md` only
   mentioned "the Hermes record" in passing. Cause: the rollout landed between handoff refreshes.
   Fix: §2 item 13 and a dedicated §3 "Hermes" block now carry it, with the rollout record linked
   and marked local-only.
3. **`HERMES_ROLLOUT_2026-11-17.md` "Still to do" is partly stale.** Its items (b) 7am note for
   `trendi-support`, (c) Studio approve/discard drafts and (d) the Ask box are all done — (b) in the
   tenant flag, (c)/(d) in commit `35f3efd`. Its (e) QA-record update is what this file partly does.
   The rollout record is left as the historical account; `HANDOFF.md` is now the worklist.

## Evidence measured this session (2026-11-17, ~14:15 NZDT)

| Check | Result |
|---|---|
| `git rev-parse --short HEAD` / `origin/main` (at measurement) | `be9a647` / `be9a647`, tree clean apart from ignored `outputs/` |
| `KEY=./Concierge ./scripts/vps/verify-deploy.sh` | `OK: repo and box agree` (api/app 110, api/static 7, scripts/vps 42, website/site 62) |
| Full API suite | **1527 passed, 19 skipped** in 20.21s (documented interpreter + shims + test DB) |
| Box health (`healthcheck.py --no-alert`) | **46 ok / 2 warn / 0 fail** — warns `inbound:onboarding` (trendibizz: owner_account, consent) and `sms:inbound` |
| Live endpoints | `trendibizz.com` 200, `/studio/` 200, `/owner/version` 200, chat demo 200 |
| Engines | `docker.service`/`docker.socket` inactive, docker disabled; production containers on Podman |
| Twenty retirement | no `trendi_crm*` volumes on Podman or in `/var/lib/docker` |
| Studio pipeline route | `/owner/crm/pipeline` → 401 (present, auth-guarded); `/studio/` serves `index-CVPc7Ilw.js` |
| Hermes gateway | container running (restarts 0), `healthz` 200, host network, read-only, cap_drop ALL |
| Hermes customer container | `hermes-trendi-support` healthy; `api_server` tools = todo, memory, session_search only |
| Hermes activity | `hermes_actions` 0 rows, `hermes_case_state` 0 rows, `hermes_tenant_settings` 0 rows (defaults to shadow/0.8) |
| `trendi-support` 7am note | `daily_summary = true`; measured new_leads 0, overdue tasks 0, waiting leads 0 → `daily_text` correctly returns None, so **no email was due**; no `daily:*` outbox row. No log distinguishes "ran and was quiet" from "never ran". |
| Version 1 announcement | no `release:*` outbox rows — still **not sent**; dry-run lists 4 tenants, 3 sharing `admin@trendibizz.com` |

## Live state in one line

Production is green on Podman, the repo and box match at `be9a647`, Twenty is gone, the Studio
pipeline board is live, and Hermes is **deployed but idle**: it can authenticate and answer, but no
component calls `POST /v1/runs`, so no case has ever been planned or executed.

## Open items this pass adds or sharpens

- The customer Hermes container runs the floating `nousresearch/hermes-agent:stable` tag (currently
  v0.23.1); the internal auxiliary is digest-pinned to v0.23.0. Pin the customer image before relying
  on it.
- `verify-deploy.sh` compares `api/app`, `api/static`, `scripts/vps` and `website/site` only. The
  gateway is built on the box from `concierge-stack/{hermes-gateway,core-rs}`, which is not compared,
  and `scripts/asterisk` is not compared either. A source-only change can therefore drift silently.
- `hermes tools list` on the customer container prints `install out of sync (pnpm: not installed or
  outdated)`. Tool *availability* is provably correct; this is a self-check warning to clear before
  the first real run, not a reason to change the toolset now.
- The 7am note has still never delivered, because `trendi-support` has no leads or tasks. Turning it
  on is not the test; the test is the first morning with something to report (or a seeded lead).
- **Committed code cites a file that is not in the repo.** `hermes-gateway/README.md` and
  `tests/acceptance.rs` cite `HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md`, which is git-ignored along
  with every `QA/verification/HERMES_*`. A fresh clone has dangling references. This is an operator
  decision (private docs repo vs a redacted committed summary), not something to un-ignore blindly.
