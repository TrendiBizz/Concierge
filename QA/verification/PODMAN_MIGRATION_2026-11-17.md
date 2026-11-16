# Docker -> Podman on the VPS: complete, 2026-11-17

## Rollback point
DigitalOcean snapshot `pre-podman-2026-11-17`, image id 254954106, 85.28 GB, taken live at 2026-11-16T21:16Z (10:16 NZDT),
droplet 617093658 (152.42.239.240, sgp1). The API token used was a one-day token, delete it in the DigitalOcean console.
Per-stack backups (pg_dumpall + compose files) are in `/root/podman-migration/<project>-<time>/` on the box.

## State after stage 1
- Podman 4.9.3 (netavark, crun, rootful) installed ALONGSIDE Docker 29.1.3. No `podman-docker` shim. Docker unchanged:
  25 containers before and after the install, iptables ruleset checksum identical before, during and after a Podman container.
- Moved to Podman: `dev-trendi-local` (db, api, tools, web). 70/70 tables match the pg_dumpall; web on 127.0.0.1:8793 returns 200.
- Still on Docker: everything else, including production (`trendi`, `trendi-hermes-*`, `asterisk`, `dev-concierge`, auxiliary).

## Defects found (each with cause, fix, proof)
1. **ufw blocks container DNS.** Containers got `Temporary failure in name resolution`. Cause: Podman's aardvark-dns listens on the
   bridge gateway (10.89.0.1), so a lookup is a packet INTO the host and ufw's default-deny drops it (`UFW BLOCK IN=podman1 ... DST=10.89.0.1`
   in dmesg). Docker's DNS lives in the daemon so it never needed this. Fix: `ufw allow in on podman+ to any port 53` (DNS only, only on
   Podman bridges), now applied by the migration script. Proof: `getent hosts db` from a container -> 10.89.0.2 after the rule; API started.
2. **Podman splits exec-form healthchecks on spaces.** `test: [CMD, python, -c, "import urllib.request; ..."]` became `python -c import`
   (SyntaxError), so a healthy API stayed `unhealthy` and compose refused to start its dependants. Fix: `[CMD-SHELL, "..."]`.
   Applied to `/opt/dev/trendi-local/compose.yml` (a box-only dev file; original kept in the backup dir). Proof: api (healthy), web 200.
   **`scripts/vps/compose.yml:93` (the production API) has the same pattern and must be converted before that stack moves.**
3. **My migration script's rollback never ran.** `trap ... ERR` without `set -E` does not fire for failures inside functions, so a failed
   `up` left the stack half on Podman. Fix: `set -Eeuo pipefail`. Proof on a throwaway stack: unhealthy -> `FAILED: putting migtest-a back on
   Docker`, container back on Docker, none on Podman. The script now also refuses (before stopping anything) any exec-form healthcheck with a
   space; proof: throwaway stack kept running, refusal message printed.
4. A piped `| tail` hid the script's exit code and its progress for 10 minutes; run it without a pipe or write to a log file.

## Defects found during the production move (attempt 3, 2026-11-17)

5. **Two `--filter label=...project=` flags are ANDed, not ORed.** `docker ps -aq --filter
   label=com.docker.compose.project=trendi --filter label=com.docker.compose.project=asterisk` matches containers carrying
   BOTH labels (none), so the volume list came back empty and nothing would have been copied. Cause: Docker's `--filter` on one
   command is a conjunction. Fix: query each project separately and merge
   (`{ docker ps -aq --filter label=...=trendi; docker ps -aq --filter label=...=asterisk; }`), already in `podman-migrate-prod.sh`.
   Proof: attempt 3's volume loop enumerated and copied the 7 `trendi_*` volumes (log: `volume trendi_database copied (86M)`, etc.).

6. **IPAM race for the PBX's fixed address.** The PBX owns `172.30.91.2` (pjsip.conf, ASTERISK_PEERS), but IPAM hands the lowest
   free address to whichever container starts first, so the unpinned bridge/shell took `.2` and the PBX died with "Address already
   in use" (attempts 1 and 2, and their rollbacks). Fix: pin bridge `.4` (`scripts/asterisk/compose.yml`) and telephone shell `.3`
   (`scripts/vps/compose.yml`); PBX stays `.2`. Proof: with all three pinned, no container can take another's address (see defect 7
   for why the ordering dance was then removed).

7. **Podman's compose refuses to recreate `trendi-api-1` while `trendi-social-1` depends on it via `network_mode: service:api`.**
   Attempt 3 held the shell back with `ptdc up -d --scale shell=0`, started asterisk, then added the shell back with a plain
   `ptdc up -d`. Re-adding a scaled-to-0 service makes Podman's docker-compose path recreate the whole project, and the recreate
   of `trendi-api-1` is refused: `Error response from daemon: container <id> has dependent containers which must be removed`
   (the dependent is `trendi-social-1`, which shares the api's network namespace). Docker's daemon handles this by removing and
   recreating the dependent too; Podman's compat API does not. The script's rollback used the same two-step and its `tdc up -d`
   (shell) DID succeed under Docker, confirming the failure is Podman-specific. Fix: drop the `--scale shell=0` two-step entirely
   — all three phone-network addresses are now fixed (defect 6), so the race it guarded against cannot recur, and the whole trendi
   stack (shell included) is started in one `ptdc up -d`, then asterisk. Proof (fails without fix): attempt 3 log shows the daemon
   error at `==> starting the telephone shell`, then `!!! FAILED`. Proof (passes with fix): re-run starts trendi+asterisk+shell
   under Podman in one pass and reaches `trendi and asterisk are running under Podman` (see the re-run log below).

## Production move complete (attempt 4, 2026-11-17)
Attempt 3 failed on defect 7. With the fix (`4aa9975`) the re-run succeeded: each stack now starts in one `up`, and the run
reached `trendi and asterisk are running under Podman` with all 13 containers (trendi + asterisk) healthy. Verified like a
customer: `owner/version`, `/studio/` and `trendibizz.com` all 200; SIP probe `no answer (dropped)`; `pjsip show registrations`
shows `concierge-reg ... Registered (exp. ~3562s)`; `iptables -L FORWARD -n` shows TRENDI-SIP ahead of NETAVARK_FORWARD;
healthcheck 0 fail. Docker's data at `/var/lib/docker` was never modified.

8. **Docker kept being re-pulled up by the host's timer services.** After the move, `docker` was stopped and `/run/docker.sock`
   symlinked to `/run/podman/podman.sock`, but `docker.service` kept coming back `active`, recreating the socket and undoing the
   symlink. Cause: the box's `/etc/systemd/system/trendi-{backup,meta-review,restore-test}.service` still carried
   `Requires=docker.service` from the 2026-11-08 Docker setup; `trendi-meta-review.timer` fires every 20 s, so each fire re-pulled
   Docker. The repo already had the fixed units (`Requires=podman.socket`) — they had just never been copied to
   `/etc/systemd/system/`. Fix: deployed the repo units (commit `d47eeab`) and `systemctl daemon-reload`. Proof: after the fix,
   `docker.service`/`docker.socket` stay `inactive` across multiple meta-review timer fires and the symlink stays intact.

9. **`trendi-sip-firewall.service` ordered itself after Docker and wanted it.** `After=docker.service` + `Wants=docker.service`
   would restart Docker at boot (undoing the symlink and its iptables chains) and ran before Podman's netavark created
   NETAVARK_FORWARD, so the TRENDI-SIP jump could not be guaranteed ahead of it. Fix: `After=network-online.target
   podman-restart.service podman.socket` and no `Wants=docker`, in `harden_host.sh` (the canonical source that writes the unit).
   Proof: after `systemctl reboot` the service is `active`, `iptables -L FORWARD -n` shows TRENDI-SIP at line 1 ahead of
   NETAVARK_FORWARD, and docker stays disabled.

10. **`meta-review-worker.py` hardcoded Docker's volume path.** It opened
    `/var/lib/docker/volumes/trendi_social/_data/social.db`, which is gone after the move. Fix: resolve the mountpoint at run time
    with `docker volume inspect trendi_social --format '{{.Mountpoint}}'` — the `docker` CLI follows the `/run/docker.sock` symlink
    to whichever engine owns the volume. Proof: the command now returns `/var/lib/containers/storage/volumes/trendi_social/_data`,
    and `social.db` is present there.

11. **Stock `podman-restart.service` only restarts `restart-policy=always`; every compose service uses `restart: unless-stopped`.**
    `podman ps -a --filter restart-policy=always -q` matched 0 containers and `...=unless-stopped` matched 25, so the stock unit's
    `podman start --all --filter restart-policy=always` would start nothing after a reboot. Fix: drop-in
    `scripts/vps/podman-restart.service.d/unless-stopped.conf` (installed to `/etc/systemd/system/podman-restart.service.d/`)
    overrides ExecStart/ExecStop to filter `unless-stopped`. Proof: with the override the reboot test below brought back all
    containers; without it the filter matched 0.

## Reboot test (the real proof)
Rebooted the droplet after the move. After boot: the `/run/docker.sock` symlink persisted (tmpfiles.d `L+` rule), Docker stayed
`inactive` + `disabled`, `podman-restart.service` brought all 13 production containers back (`restart: unless-stopped`), the SIP
firewall came up with the jump ahead of NETAVARK_FORWARD, `concierge-reg` re-registered with the carrier (`Registered`,
exp. ~3551 s), endpoints 200, healthcheck 0 fail. `docker` CLI + the compose plugin stay installed as the client for Podman's
socket.

## Still open
- `network_mode: host` (hermes-gateway) under Podman's compose path, and the digest-only Hermes image, were not part of this move.
- cap_drop/cap_add choices for the customer Hermes container need a re-test on Podman (already flagged in the Hermes record).
- Docker must stay installed (disabled, not purged) for at least a week.
- Operator items: delete the one-day `podman-snapshot` DigitalOcean token; approve or decline the Version 1 announcement email;
  check tomorrow after 07:00 NZDT whether the first `trendi-support` morning email went out.
