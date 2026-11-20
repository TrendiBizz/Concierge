# SESSION HANDOFF 2026-11-19b

## Git
main, local commits NOT pushed: 138ddea (quote-guard written prices, booking confirm key, dup-race) and 2b73d60 (scripts/dev/test-db.sh + QA/verification/TEST_DB_2026-11-19.md). Before that origin/main = 3eea77b. Not deployed. Rules: env -u GIT_CONFIG_COUNT git; git pull --rebase, then push, then KEY=./Concierge ./scripts/vps/verify-deploy.sh. Ask Jo before push/deploy.

## Done
- PR #1 (TrendiBizz/Concierge) was already MERGED 2026-11-04 (010db79); reviewed booking.py/guard.py on main, fixed 3 findings with tests + mutation check (QA/verification/BOOKING_GUARD_REVIEW_FIXES_2026-11-19.md). Other 23 PR files NOT reviewed.
- Test Postgres: Mac had no docker/podman/Postgres. brew installed postgresql@17+pgvector; scripts/dev/test-db.sh starts cluster on 127.0.0.1:55433 (postgres/pw, data ~/work-staging/pgdata-concierge-test). Full suite 1534 passed, 19 skipped. Run the script after reboot.

## NEXT ACTION (Jo ask, unanswered)
Jo: "if we are using podman i want to know why there is still searches for docker, this must be fixed". Investigate: grep repo (scripts/vps/*.sh, healthcheck.py, backup-all.sh, watchdog.py, redeploy-api.sh, deploy-api.sh, docker-compose.yml, systemd units, cron, docs) for `docker`; read QA/verification/PODMAN_HANDOFF_2026-11-17.md and PODMAN_MIGRATION_2026-11-17.md to learn whether the VPS migration to Podman actually finished (attempt 3 outcome). Note the planned design keeps the `docker` CLI as client to Podman's socket via /run/docker.sock symlink, so some `docker` calls are by design; decide which are stale vs intended, switch to podman where the migration is complete, with tests. Unknown: whether VPS is really on Podman (check box read-only via ssh KEY=./Concierge; never docker compose down -v; never stop trendi/asterisk). Mac has no container runtime now.

## Traps
Caveman replies. Never print secrets. Never hand-edit bots.json/routines.json. Edits on the box must come back to repo same session. Test cmd: cd api && PYTHONPATH="$(cd .. && pwd)/QA/verification/shims" TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres /Users/jo/work-staging/venv-concierge/bin/python -m pytest -q
