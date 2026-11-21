# Working agreement — Trendi Concierge

Every session reads `docs/AGENT_WORKING_ORDER.md` and `hermes/README.md` first. Commit Hermes lane briefs
under `docs/`; the container reads this repo at `/opt/data/work`. Full text of every rule, incident and
command below: `docs/AGENTS_DETAIL.md` (read the section you need). Startup files have a size budget:
`scripts/dev/startup-budget.sh` (keep this file, `HANDOFF.md` and the handoff small; history goes to `docs/archive/`).

**This repository is the only place work lives.** One repo, one history, one deploy path. Uncommitted or
box-only changes are lost or silently diverge. "It works" and "it is what we committed" are different questions.

## Deploy rule (Jo, 2026-11-21)
- All deploys go only through the repo scripts: `scripts/vps/deploy-api.sh`, `deploy-site.sh`, `sync-tooling.sh`, `verify-deploy.sh`; `scripts/seo-gate.sh` must print `GATE RESULT: PASS`.
- Never put raw `docker`, `docker compose`, `podman` or `podman-compose` commands in plans, prompts, docs or proposals.
- If a one-off container step is needed (e.g. `alembic stamp`), add it to a repo script first, then reference the script.

## Where things live
- Canonical local clone: `~/trendi-site` (TrendiBizz/Concierge `main`). Deploy from here: `cd ~/trendi-site && KEY=<path to deploy key> ./scripts/vps/deploy-site.sh`. The GitHub repo Trendiisales/trendi-site is stale (Cloudflare-era); do not use it.
- Website source: `website/` (only source) → `scripts/vps/deploy-site.sh`
- API: `api/app/`, `api/static/` → `scripts/vps/deploy-api.sh`
- Host tooling: `scripts/vps/` → `scripts/vps/sync-tooling.sh`
- QA records: `QA/verification/` (one dated file per piece of work: cause, fix, proof)
- Box `152.42.239.240`, release `20261108-vps`; paths under `/opt/trendi/releases/20261108-vps/`

## Non-negotiables
0. Site SEO contract: `python3 scripts/seo/site_seo.py check` gates every deploy; never bypass, never hand-edit the sitemap (`sitemap --write`).
1. Never edit the box and walk away; bring the fix back into this repo, with a test, same session.
2. Never publish from a directory that is not this repo; deploy refuses a dirty tree.
3. Commit before you deploy.
4. Run `KEY=./Concierge ./scripts/vps/verify-deploy.sh` before saying "deployed" (exit 0 = repo and box agree). Drift: deploy the repo or commit the box state. No third option.
5. Every defect: fixed, tested, documented (cause, fix, proof) the same session; mutation-check the test once.
6. Never verify a mail fix by replaying to production; never send real SMS or place real calls to test.

## Branches and pushes
`main` is deployed. `git pull --rebase` before pushing (shared repo + checkpoint bot); push only after the full suite passes:
`scripts/dev/test-db.sh` first, then
`cd api && PYTHONPATH="$(cd .. && pwd)/QA/verification/shims" TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres /Users/jo/work-staging/venv-concierge/bin/python -m pytest -q`
Re-run `verify-deploy.sh` after pushing. If every git command fails with `missing config key GIT_CONFIG_KEY_0`, prefix git with `env -u GIT_CONFIG_COUNT` (harness fault, not the repo; see `docs/AGENTS_DETAIL.md`).
