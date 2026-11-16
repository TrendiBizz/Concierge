# Docker -> Podman on the VPS: stage 1, 2026-11-17

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

## Known risks still open for the production stacks (INFERENCE, unverified)
- `network_mode: service:api` (social) and `network_mode: host` (hermes-gateway) under Podman's compose path.
- `trendi-sip-firewall.service` hooks Docker's iptables chains; Asterisk needs UDP 5060 and 10000-10099 through Podman's netavark rules.
- Digest-only images (internal Hermes, rollback candidates) must be moved with `docker save | podman load` (the script does this).
- cap_drop/cap_add choices made for Hermes under Docker need a re-test on Podman.
- Reboot behaviour: `podman-restart.service` is not enabled yet; `restart: unless-stopped` containers will not come back after a reboot
  until it is.
- Docker must stay installed (disabled, not purged) for at least a week after the last stack moves.
