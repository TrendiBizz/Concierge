# Hermes master — Trendi / Concierge operations

This directory is the source of truth for **Hermes as the owning agent** of Trendi
(trendibizz.com) and Concierge operations. It replaces the Grok Bot schedules and
procedures that were moved to OpenBot Workwatch on the Mac.

Nothing here sends, posts, deploys or spends. Every routine produces a report or a
draft; Jo's yes is still the gate for anything external.

## Shape

```
                 trendi-master            (owns the worklist and the morning brief)
                 /     |      \    \
        seo-engine  trendi-desk  pen-test  site-watch  workwatch
        (SEO/AEO)   (copy/social) (appsec)  (integrity) (automation review)
```

Each name is a real Hermes **profile** with its own `SOUL.md`, memory and
`cron/jobs.json`. Each routine is a cron job on one of those profiles. The master
profile reads the subagents' reports each morning and produces one brief with the
decisions that need Jo.

This is the Hermes equivalent of the Grok Bot shape: one boss, persistent named
helpers, and one schedule per job.

## Where it runs

**Mac, in `hermes-concierge`** — because the work itself is there: the
`trendi-seo` toolchain, the `trendi-site` deploy gate, `jo-brain`, the Workwatch
reports and the API keys in `~/.config/trendi*`. The container is loopback-only
with `no-new-privileges` and no Docker socket.

**The VPS customer Hermes stays separate and restricted.** `hermes-trendi-support`
is the per-tenant planner with only todo, memory and session_search. It is not the
master and it does not get these tools. The master may write a draft for a customer
case through the Concierge API, but the gateway's shadow/approval rules still apply.

**Deliberately not mounted:** the Concierge repo's SSH key, the VPS root key, the
Docker socket, the Keychain, and the rest of `$HOME`. Deploying the Concierge API
remains a human action. The site deploy gate stays in `trendi-site` and is not run
by an unattended routine.

## What moved

| Grok automation | Hermes routine | Profile | Status |
|---|---|---|---|
| Daily site + search monitor (Trendi) | `seo-daily-monitor` | seo-engine | active |
| Weekly SEO cycle (Trendi) | `seo-weekly-cycle` | seo-engine | active |
| Monthly SEO audit (Trendi) | `seo-monthly-audit` | seo-engine | active |
| Innovation scout (Trendi) | `seo-innovation-scout` | seo-engine | active |
| Trendi LinkedIn weekly draft | `trendi-linkedin-weekly` | trendi-desk | active |
| Trendi biweekly SEO + pen-test news | `trendi-biweekly-news` | trendi-desk | active |
| Trendi daily SEO / pen-test social drafts | `trendi-social-drafts` | trendi-desk | active |
| Trendi SEO forums daily deep dive | `trendi-deep-dive` | trendi-desk | active |
| Twice-monthly post brief (Trendi) | `trendi-post-brief` | trendi-desk | active |
| trendibizz.com daily tamper watch | `trendi-tamper-watch` | site-watch | paused — kit in `scripts/security/tamper/`; needs Pages Read and DNS confirmation |
| Ego Lite Linux watch | `ego-lite-linux-watch` | trendi-desk | paused — one-shot; re-enable when there is a Linux build |
| Workwatch weekly report | `workwatch-weekly-report` | workwatch | active — notes mounted read-only |
| — (new) | `master-daily-brief` | trendi-master | active |
| — (new) | `master-weekly-review` | trendi-master | active |

The Grok **Omega** bots (Omega Boss, Omega Harness, Omega Auditor, Edge Scout, and
the trade routines) are a separate project and are not part of this migration.

## Install

```bash
# 1. Start the Mac runtime with the work mounts (idempotent; replaces the old container)
./hermes/runtime/start-master.sh

# 2. See the plan, then apply it inside the container
docker exec hermes-concierge /opt/data/venvs/hermes-tools/bin/python \
  /opt/data/work/hermes/install.py --dry-run
docker exec hermes-concierge /opt/data/venvs/hermes-tools/bin/python \
  /opt/data/work/hermes/install.py --apply

# 3. Verify
docker exec hermes-concierge hermes profile list
docker exec hermes-concierge hermes -p seo-engine cron list --all
```

The runtime script creates the `hermes-tools` venv (PyYAML) and the
`trendi-seo` Linux venv on first start. The image is `nousresearch/hermes-agent:stable`
by default; for reliability set `HERMES_IMAGE` to the digest printed at the end of the
start, so a restart cannot change the agent underneath the schedules.

`install.py` is idempotent: an existing profile is kept and its SOUL refreshed; an
existing job with the same name is skipped unless `--force` is given.

## Tests

```bash
/Users/jo/work-staging/venv-concierge/bin/python hermes/test_manifest.py
```

It checks the manifest, every procedure, the master/subagent mapping, the guards,
the cron expressions and the absence of secret-shaped strings. It does not call a
model or the network.

## Rollback

```bash
docker exec hermes-concierge hermes cron pause <id>        # stop one routine
docker exec hermes-concierge hermes -p <profile> cron remove <id>
docker exec hermes-concierge hermes profile delete <profile> -y
docker rm -f hermes-concierge                              # stop the master
```

The data volume `hermes_concierge_data` is kept. Nothing on the Mac is deleted by
rollback; the mounted repos and reports are untouched.

## Files

- `AGENTS.md` — the shared standing policy injected into every job's workdir.
- `schedules.yaml` — profiles, routines, cron schedules, status and source.
- `profiles/<name>/SOUL.md` — the master and subagent roles.
- `routines/<id>.md` — the procedure a job runs.
- `install.py` — creates profiles, writes SOULs, registers cron jobs.
- `test_manifest.py` — the checks above.
- `runtime/start-master.sh` — the Mac container with the work mounts.
