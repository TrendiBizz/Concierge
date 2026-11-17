# Hermes report persistence and schedule parity — 2026-11-18

Scope: local branch and local Docker Desktop container only, per
`docs/HERMES_PARITY_BRIEF_2026-11-18.md`. No production verification or deployment.

## Cause and evidence

- `trendi-social-drafts`, job `d99f7a4cfc02`, output
  `/opt/data/profiles/trendi-desk/cron/output/d99f7a4cfc02/2026-11-18_07-01-15.md`:
  returned drafts and claimed reports/latest/social files saved. None exist.
  Read-only state.db inspection of session
  `local-c8e92f28d58025e143468bd428e6d606b6657158c7134e495b61998c36f6520d`
  showed terminal directory/read operations and read_file, no file-writing call.
- `trendi-deep-dive`, job `783c4ab699a0`, output
  `/opt/data/profiles/trendi-desk/cron/output/783c4ab699a0/2026-11-18_07-31-26.md`:
  returned findings and claimed saved report/delta/latest, none exist. Session
  `local-e6fce2fac9909b86a1f114439f6a1c85ae1ecbeef3628d78ef7814f1b63f5043`
  had only two terminal checks, no write call. Both procedures had ambiguous
  relative canonical copy destinations and lacked verified-write completion.
  Cron `ok` means execution completed, not that the report contract was met.
- `seo-daily-monitor`, job `4c2123e49cf0`: reported absence is NOT reproducible.
  `/opt/data/.workwatch/reports/hermes/seo-engine/2026-11-18-seo-daily-monitor.md`
  exists with mtime 2026-11-18 07:43:27.713661 NZDT, before cron output at 07:43:33.
  Session `local-abc7430146c9db8a791f7e32cd716fb0902899f2e856e63457e72d7cc7d6c852`
  has two write_file calls. No evidence of a UTC/permission/path failure in this run.
  The earlier observation may be stale or from another view; cause is unverified.

## Fix

Every procedure and generated prompt now names the absolute canonical dated report,
current Pacific/Auckland date, actual write tools, latest copy, read-back and explicit
failure response. Quiet/blocked runs must persist too. The weekly master filename
now follows the same contract. No reports were created or backfilled by this task.
Added defensive weekly advisory routine, lane mapping, README, four retimings and
root standing pointers. All other schedule strings remain unchanged.

## Proof

`/Users/jo/work-staging/venv-concierge/bin/python hermes/test_manifest.py`:
26 tests pass. Before fixes the report contract test failed for all 14 original
procedures. Mutation removed generated prompt read-back instruction: test failed;
restoring it returned green. Initial mutation exposed a test weakness (procedure
text masked the missing prompt instruction); test now checks prompt preamble alone.
Static contract checks do not prove future model compliance; scheduled runs remain
the end-to-end persistence check. No jobs replayed and no research claims verified.

Evidence logs: `~/jo-jobs/hermes-parity/test-red.txt`, `test-mutation.txt`,
`test-green.txt`, `install-dry-run.txt`; final runtime evidence in `result.md`.

## Local container verification

Docker context `desktop-linux`, container `hermes-concierge`: installer dry-run then
apply exited 0, 14 replacements plus one new job, without `--force` (hash changes
already select every changed procedure). All six `hermes -p <profile> cron list
--all` commands exited 0. Parsed lists match the manifest exactly: 15 unique jobs,
14 active and Ego Lite still paused, timezone Pacific/Auckland throughout. New
advisory next run 2026-11-25T09:00:00+13:00. Exactly the four approved existing
schedule strings differ from main. Second dry-run skips all 15 jobs.
Full schedules/next runs: `~/jo-jobs/hermes-parity/cron-summary.md`; raw lists in
`cron-<profile>.txt`, apply log `install-apply.txt`. No push or production access.
