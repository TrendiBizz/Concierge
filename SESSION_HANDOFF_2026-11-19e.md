# SESSION HANDOFF 2026-11-19e

## Git
main == origin/main (pushed, suite 1536 passed). Pushed: 138ddea, 2b73d60, 8c286d8, ac386e8, + harden_host journald commit (api/tests/test_harden_host_podman.py). Use `env -u GIT_CONFIG_COUNT git`.

## Done
- Docker audit: box = Podman only (docker daemon inactive, /run/docker.sock -> podman.sock; docker CLI by design). Fixed wording (hermes.sh, scripts/vps/README.md). harden_host.sh now caps journald (SystemMaxUse=1G) instead of dead docker json logrotate; applied on box (/etc/systemd/journald.conf.d/trendi-cap.conf), removed /etc/logrotate.d/docker-containers.
- sync-tooling.sh run: scripts/vps matches box.

## DEPLOY STATE
verify-deploy.sh = FAIL drift: api/app on box lacks 138ddea (booking.py, config.py, automation.py, case_planner.py...). Needs `scripts/vps/deploy-api.sh` then `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. NOT run: Jo has not said go (production). Ask/confirm, then deploy.

## NEW ASK from Jo (NOT STARTED)
1. "Issues with openmaus and trendibizz: missing connections/permissions; find and fix."
2. SMS issue still unresolved.
3. Context: Concierge reports trendibizz lacks an owner account and permission to read incoming email. Asking Jo to sign in when the account is missing was premature; first establish how to complete that setup (separate from the SMS test).
Next: read QA/verification (mail/SMS/owner records), hermes/README.md; find where Concierge reports "no owner account"/"cannot read incoming email" (api/app grep owner/inbound mail permission); check tenant trendibizz + openmaus config on box read-only; propose fix; no real SMS/calls (rule 6); no replay of mail to prod.

## Other open
- Mac concierge-stack/ + scripts/*.sh docker calls unclassified.
- Token baseline compare (51k), non-Claude agent measure, Jo to disable claude.ai connectors.

## Traps
Caveman replies. Never print secrets. No `docker compose down -v`; never stop trendi/asterisk. Test DB: scripts/dev/test-db.sh first. New thread at handoff.
