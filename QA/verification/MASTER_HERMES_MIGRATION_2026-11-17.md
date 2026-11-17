# Hermes master + subagents: Trendi / Concierge migration — 2026-11-17

## What was asked

Jo: "ensure Hermes is now the agent in charge of all of our Concierge/trendibizz work.
I want all of the grok bot schedules/procedures moved to Hermes in the same format so we
have a master and the subagents as we do with Grokbot." Sequential, with proper testing.

## What was built

- `hermes/` in the Concierge repo: `schedules.yaml`, the standing policy, six profile
  SOULs, fourteen routine procedures, an idempotent installer, 23 tests, and the Mac
  runtime script.
- **Six Hermes profiles on the Mac** (`hermes-concierge`, loopback only):
  `trendi-master` (master), `seo-engine`, `trendi-desk`, `pen-test`, `site-watch`,
  `workwatch` (subagents).
- **Fourteen cron jobs**: twelve active, two paused with a recorded reason
  (`trendi-tamper-watch`, `ego-lite-linux-watch`).
- **Twelve Grok Trendi automations mapped** in `hermes/JOBS.md` and
  `schedules.yaml#grok_automations`. The Omega bots are a different project and are not
  part of this move.
- **The old Workwatch launchd routines disabled** (six labels), so Hermes is the only
  local scheduler.
- **Hermes dashboard enabled** at `http://127.0.0.1:9120` (loopback only, password
  login, s6-supervised) with Chat, Sessions, Cron and Config pages; `trendi-master` is
  the default profile.
- **Workwatch weekly is active** (Mon 08:00): the notes are mounted read-only and the
  first report is `Status: quiet` for 2026-11-10..16.
- **The VPS customer Hermes is unchanged.** `hermes-trendi-support` stays restricted to
  todo, memory and session_search. The Mac master is the operator agent, not the
  customer planner.

## Live install (2026-11-17, NZDT)

| Check | Result |
|---|---|
| `hermes profile list` | default + 6 profiles, all served by the gateway |
| `hermes -p seo-engine cron list --all` | 4 active; next run 2026-11-18 07:40 |
| Scheduler proof | `scheduler-probe` fired 14:34:11, output `2026-11-17T01:34:11Z`; job and script then removed |
| Model proof | `hermes -p trendi-master -z "Reply with exactly: HERMES-OK"` → `HERMES-OK.` |
| Real monitor | `monitor/daily_monitor.py` in the container: 92.2s first run, 62.6s later; JSON verdict returned |
| SEO job | `seo-daily-monitor` wrote `seo-engine/2026-11-17-seo-daily-monitor.md` (377 bytes) quoting the verdict |
| Master job | `master-daily-brief` wrote `trendi-master/2026-11-17-master-daily-brief.md` (729 bytes), `Status: attention`, naming the lanes that have no report |
| No fabrication | after the fix, the other lanes still have **no** `latest.md`; the master did not create them |
| Dashboard | `http://127.0.0.1:9120` returns the sign-in page; password login 200; `/api/auth/me` = `jo`; s6-supervised |
| Workwatch run | `workwatch-weekly-report` ran 15:10, wrote a 481-byte `Status: quiet` report for 2026-11-10..16 |

## Workwatch and the dashboard (added after the first install)

- **Workwatch is active.** `~/.workwatch/notes` is mounted read-only into the container
  at `/opt/data/.workwatch/notes`; `workwatch-weekly-report` is enabled (Mon 08:00, job
  `b8c9000b442b`). A live run read the 8-day window, reported 7 days, and wrote
  `~/.workwatch/reports/hermes/workwatch/latest.md` (481 bytes, `Status: quiet`). The
  master's lane table now expects a workwatch report like any other active lane.
- **The dashboard is the chat UI.** `http://127.0.0.1:9120` serves the Hermes web
  dashboard (Chat, Sessions, Cron, Config, Analytics, Channels) behind a password. The
  username is `jo`; the password is generated once into
  `concierge-stack/hermes/hermes.env` (mode 600), with
  `HERMES_DASHBOARD_BASIC_AUTH_SECRET` for stable sessions. It is published on the Mac
  loopback only (`127.0.0.1:9120`), not the LAN or internet, and is supervised by s6 so
  it survives a container restart.
- **Security note:** while probing the login endpoint, a 422 validation response echoed
  the generated password. The password was rotated immediately, the container restarted,
  and the new login was re-verified (200 + `/api/auth/me` = `jo`). A password probe must
  send the response to `/dev/null` and print only the status; never print the body.

## Defects found and fixed (cause, fix, proof)

1. **PyYAML was missing from the container's system Python**, so the installer died at
   "PyYAML is required". Fix: the runtime creates `/opt/data/venvs/hermes-tools` with
   PyYAML and runs the installer with it. Proof: install completed; `import yaml` 6.0.3.
2. **The Trendi scripts hardcode `/Users/jo/...`.** Inside the Linux container those
   paths did not exist. Fix: `/Users` is created and `/Users/jo` is a symlink to
   `/opt/data`, where the Mac directories are mounted at the same relative layout.
   Proof: `/Users/jo/OpenBot/Shared/trendi-seo/monitor/daily_monitor.py` and both key
   files resolve; the monitor ran.
3. **Each Hermes profile gets its own HOME, so `Path.home()` could not see the keys.**
   The first SEO agent worked around it by **copying** `serper_api_key` and
   `gemini_api_key` into its profile home (53 and 40 bytes). Fix: the installer creates
   read-only symlinks for `.config/trendi`, `.config/trendi-seo`, `.workwatch`,
   `OpenBot` and `jo-brain`; the copied key files were deleted. Proof:
   `Path.home()/".config/trendi/serper_api_key"` exists at 40 bytes through the link;
   no copies remain. The policy now explicitly forbids copying a key.
4. **The report directory was root-owned, so the agent could not write its report.**
   The job's response was delivered and the agent claimed "Report written", but the file
   stayed at the old 14:40 copy. Fix: `chmod -R a+rwX` on the mounted
   `reports/hermes` tree (and in the runtime script). Proof: the next SEO run wrote a
   new 377-byte report at 14:49 with the new verdict.
5. **The installer printed the whole plan twice on `--apply`.** Fix: the plan is only
   printed in dry-run; apply prints the actions it performs. Proof: the apply output now
   has one block.
6. **The master fabricated four "quiet" subagent reports.** It created
   `pen-test/latest.md`, `site-watch/latest.md`, `trendi-desk/latest.md` and
   `workwatch/latest.md` with specific false claims ("No new CVEs", "No integrity
   alerts"). This violated the standing policy. Fix: the four fakes were deleted; the
   master now receives a deterministic `LANE STATUS TABLE` from
   `hermes/scripts/lane_status.py`, which only accepts a **dated routine report**
   younger than 36 hours, ignores a bare `latest.md`, and marks paused/no-routine lanes;
   the routine and SOUL forbid writing outside `trendi-master/`. Proof: the next master
   run wrote `Status: attention`, named the missing lanes from the table, and left the
   other lanes with no files. Tests cover a placeholder, a real report and a stale one.
7. **The master called itself `quiet` while lanes were unanswered.** Fix: `quiet` only
   when every lane has a fresh report and none needs Jo; `attention` otherwise. Proof:
   the final brief is `attention`.
8. **The master asked Jo to initialise its own report directories.** Fix: explicit
   instruction not to ask about its own plumbing; a missing lane is `UNANSWERED`. Proof:
   the final brief has no such question.
9. **The first SEO report claimed "all normal" without the verdict.** Fix: the procedure
   requires quoting `status`, `items`, `run_at` and `seconds`. Proof: the final report
   quotes `status=quiet, items=[], run_at=2026-11-17T14:48:01+13:00, seconds=62.6`.

## Tests

`hermes/test_manifest.py` — **23 passed**:

- manifest shape, unique ids, profile/SOUL presence, schedule/timezone validity;
- every Grok Trendi automation mapped once; every non-master routine mapped;
- approval guard in every procedure; no secret-shaped strings;
- installer plan is pure, replaces on hash change, skips on a match, filters by `--only`;
- profile-home links are symlinks, a real directory is not deleted;
- the master's `lane_status.py` mapping matches the manifest;
- a placeholder `latest.md` is not evidence; a real dated report is; a 48-hour-old report
  is not.

The scheduler proof is the live job above; the reporter proof is the two live reports.

## Open items

1. **Pause the remaining Trendi automations in Grok Bot.** The Workwatch launchd copies
   are disabled, but the Grok cloud copies cannot be paused from this repo. Jo must pause
   (not delete) in Grok Bot: Daily site + search monitor, Weekly SEO cycle, Monthly SEO
   audit, Innovation scout, Trendi LinkedIn weekly draft, Trendi biweekly SEO + pen-test
   news, Trendi daily SEO / pen-test social drafts, Trendi SEO forums daily deep dive,
   Twice-monthly post brief, trendibizz.com daily tamper watch, Ego Lite Linux watch.
   Until they are paused, they may double-run with Hermes.
2. **First scheduled Hermes runs:** 2026-11-18 07:00 social drafts, 07:30 deep dive,
   07:40 daily monitor, 08:00 master brief. Check their reports and the master brief.
3. **The daily monitor's first manual run flagged** `/sitemap.xml` and `/llms.txt`
   changed with no `changes.csv` row, and two new queries. The test re-runs seeded the
   state, so the current report is quiet. Verify the change was planned before trusting
   the next quiet run.
4. **Tamper watch is paused**: needs a read-only Cloudflare token and the tamper kit in
   `trendi-site/scripts/security/`.
5. **Workwatch weekly is DONE** (2026-11-17): `~/.workwatch/notes` is mounted read-only
   at `/opt/data/.workwatch/notes`, the job is active (Mon 08:00, id
   `b8c9000b442b`), and the first report is `Status: quiet` for 2026-11-10..16. The
   report is at `~/.workwatch/reports/hermes/workwatch/latest.md`; the job is visible in
   the dashboard's Cron page and the `workwatch` profile is selectable in Chat.
6. **Ego Lite is paused**: one-shot; no Linux build.
7. **Pen Test has no scheduled routine.** The profile exists and the lane is covered by
   the biweekly news and social drafts, but the Grok Pen Test scope is still TODO(Jo).
8. **Image is `:stable`.** Pin `HERMES_IMAGE` to the printed digest for reliability.
9. **The Mac must be awake** for the schedules; `--catch-up on` runs a missed job once on
   wake. The VPS is not involved.
10. **The reports tree is `0777`** on the Mac mount so the container user can write. It
    contains no secrets, but it is world-writable; revisit if the Mac is shared.

## Commands used to verify

```bash
docker exec hermes-concierge hermes profile list
docker exec hermes-concierge hermes -p seo-engine cron list --all
docker exec hermes-concierge hermes -p seo-engine cron status
docker exec -w /Users/jo/OpenBot/Shared/trendi-seo hermes-concierge \
  /opt/data/venvs/trendi-seo/bin/python monitor/daily_monitor.py
docker exec hermes-concierge sh -lc 'cat /opt/data/.workwatch/reports/hermes/seo-engine/latest.md'
docker exec hermes-concierge sh -lc 'cat /opt/data/.workwatch/reports/hermes/trendi-master/latest.md'
/Users/jo/work-staging/venv-concierge/bin/python hermes/test_manifest.py
```
