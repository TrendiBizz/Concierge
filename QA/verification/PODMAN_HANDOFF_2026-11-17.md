# Handoff: Docker -> Podman on the VPS (written 2026-11-17 ~11:40 NZDT, mid-migration)

> **COMPLETED 2026-11-17 ~12:20 NZDT.** Production (`trendi` + `asterisk`, incl. the telephone shell) now runs
> entirely on Podman; the Docker engine is stopped and disabled (CLI + `/var/lib/docker` kept, not purged). The move
> survived a real reboot (containers came back via `podman-restart.service`, the `/run/docker.sock` symlink persisted,
> SIP still dropped). Full cause/fix/proof for every defect is in `QA/verification/PODMAN_MIGRATION_2026-11-17.md`;
> the remaining open items are its "Still open" section. Commits `4aa9975`, `d47eeab`, `b8a8641` (+ checkpoint saves).

Read `QA/verification/PODMAN_MIGRATION_2026-11-17.md` too. This file is what to DO next and what NOT to do.
Box: `root@152.42.239.240` (DigitalOcean droplet 617093658, Ubuntu 24.04). From the repo root: `ssh -o BatchMode=yes -o IdentitiesOnly=yes -i ./Concierge root@152.42.239.240`.
Repo rules (AGENTS.md) still apply: commit before deploy, `scripts/vps/sync-tooling.sh` for host tooling, `verify-deploy.sh` before saying "done".
Handover rule: this is not a finished handover until the new owner says so in the chat. Do not assume anything below is still true: CHECK FIRST.

## First 3 minutes: find out the real state (read-only)
```
docker ps --format '{{.Names}} {{.Status}}' ; echo ---; podman ps -a --format '{{.Names}} {{.Status}}'
tail -40 /root/podman-migration/prod.log          # attempt 3 of the production move; look for "script-exit" / "rolled back" / "running under Podman"
curl -s http://127.0.0.1:8000/version ; curl -s -o /dev/null -w '%{http_code}\n' https://concierge.trendibizz.com/owner/version
python3 scripts/vps/sip-probe.py   # (copy from the Mac if missing: it sends one SIP OPTIONS to UDP 5060 and must print "no answer (dropped)")
```
Never leave telephony down: if `asterisk-pbx-1` is not running, fix that before anything else (see "PBX recovery").

## What is already done (verified)
- Snapshot `pre-podman-2026-11-17` (DO image 254954106). The one-day API token used for it must be deleted in the DigitalOcean console.
- Podman 4.9.3 installed ALONGSIDE Docker (no `podman-docker` shim). ufw rule `53 on podman+` allows container DNS.
- On Podman and healthy: `dev-trendi-local`, `dev-concierge`, `trendi-hermes-trendi-support` (3 tools only), `trendi-hermes-gateway`, `trendi-auxiliary` (Kuma stays stopped, it was already).
- SIP firewall: `/usr/local/sbin/trendi-sip-firewall.sh` now also puts the TRENDI-SIP jump FIRST in `FORWARD` (Podman never reads DOCKER-USER). `healthcheck.py` fails if the jump is missing or if `NETAVARK_FORWARD` is ahead of it. Tests: `api/tests/test_healthcheck_backups.py`.
- Scripts (all in `scripts/vps/`): `podman-migrate-stack.sh` (one stack, auto rollback), `podman-migrate-prod.sh` (trendi + asterisk together).

## Production move: what happened and why it failed twice
`podman-migrate-prod.sh` did: preload images, pg_dumpall, stop trendi then asterisk on Docker, copy volumes, recreate `asterisk_phone` in Podman WITH compose labels, start trendi, start asterisk.
Trendi came up healthy under Podman both times. `asterisk-pbx-1` failed with "Address already in use": the PBX needs the fixed address `172.30.91.2` (pjsip.conf, ASTERISK_PEERS) and the bridge/shell started first and took it (IPAM gives the lowest free address). The rollback hit the same race, so telephony was down for a few minutes each time and was restored by hand.
Fixes already committed and synced: bridge pinned to `.4` (`scripts/asterisk/compose.yml`), telephone shell pinned to `.3` (`scripts/vps/compose.yml`), PBX started first, shell last. NOTE `sync-tooling.sh` does NOT publish `scripts/asterisk`; that file was copied by hand (md5 matched). Attempt 3 was started with these fixes; its result is in `/root/podman-migration/prod.log`.

## If attempt 3 failed or the stack is half-and-half
1. The script's own rollback puts both stacks back on Docker. If it did not finish, do it by hand IN THIS ORDER (PBX first):
   `docker network inspect asterisk_phone || docker network create --label com.docker.compose.project=asterisk --label com.docker.compose.network=phone --subnet 172.30.91.0/29 asterisk_phone`
   `cd .../scripts/vps && docker compose --env-file /opt/trendi/shared/compose.env -f compose.yml --profile public up -d --scale shell=0`
   `cd .../scripts/asterisk && docker compose --env-file /opt/trendi/shared/phone.env -f compose.yml -f compose.public.yml up -d pbx && ... up -d`
   then trendi again without `--scale` to start the shell. (Paths: `/opt/trendi/releases/20261108-vps/product/scripts/...`.)
2. Stale Podman volume copies (`podman volume ls | grep ^trendi_`) must be deleted (`podman volume rm`) before any retry: Docker kept writing, so they are out of date. The script refuses to run while they exist, on purpose.
3. Docker's data under `/var/lib/docker` is never modified by these scripts. Backups and a pg_dumpall are in `/root/podman-migration/prod-<time>/`.

## If attempt 3 succeeded: remaining steps
1. Verify like a customer: `https://concierge.trendibizz.com/studio/` and `/owner/version` return 200; `trendibizz.com` 200; SIP probe still "dropped" AND `iptables -L TRENDI-SIP -n -v` DROP counter rises; `asterisk -rx "pjsip show endpoints"` shows 2; `hermes.sh gateway-run` still answers; `python3 scripts/vps/healthcheck.py` all ok (the 5-minute cron runs it).
2. Make `docker` talk to Podman for cron, systemd units and scripts (`healthcheck.py`, `backup-all.sh`, `watchdog.py`, `redeploy-api.sh` all call `docker`): after the Docker daemon is stopped, `ln -s /run/podman/podman.sock /run/docker.sock` via a tmpfiles.d rule (`L+ /run/docker.sock - - - - /run/podman/podman.sock`) and `systemctl enable --now podman.socket podman-restart.service`.
3. Reboot test (this is the real proof). Before it, confirm `restart: unless-stopped` on every service you need back, and that `trendi-sip-firewall.service` runs AFTER Podman has created its chains (re-run it manually after boot if the health check says NETAVARK_FORWARD is ahead of the jump).
4. Only then stop and disable the Docker ENGINE (`systemctl disable --now docker docker.socket`). Keep the `docker` CLI and compose plugin installed: they are the client for Podman's socket. Do NOT purge `/var/lib/docker` for at least a week.
5. Update `QA/verification/PODMAN_MIGRATION_2026-11-17.md` (defects 5 and 6 below), commit, run `KEY=./Concierge ./scripts/vps/verify-deploy.sh`.
6. The Mac: Docker Desktop is running and a throwaway test database `concierge-test-pg` (pgvector, port 55433) is up; the API tests need it. Replacing Docker Desktop with Podman on the Mac is a separate job, not started.

## Hard rules while doing this
- Never put a real SMS or call through to "test". The SIP check is a single OPTIONS packet from a non-carrier address.
- Never stop trendi/asterisk without the script's rollback available. Never `docker compose down -v`.
- Do not send the Version 1 announcement email (`POST /admin/releases/announce?send=true`): it is awaiting Jo's approval.
- Secrets: never print env files. The DigitalOcean token is in the T3 secrets file and must be deleted by Jo.
- Do not give Claude data, sessions or memory to OpenBot/LMStudio (CLAUDE.md). DeepSeek is allowed.

## Defects to add to the QA record (found after the first write-up)
5. Two `--filter label=...project=` flags are ANDed, not ORed (matched nothing). Query each project separately.
6. IPAM race for the PBX's fixed address (above). Plus: `sync-tooling.sh` does not cover `scripts/asterisk`; verify-deploy does not either.

## Still open from the earlier work
- Tomorrow after 07:00 NZDT: did the first morning email go out for `trendi-support` (only sends if something needs attention)?
- Version 1 announcement preview lists 4 recipients, 3 of them `admin@trendibizz.com` (duplicates).
