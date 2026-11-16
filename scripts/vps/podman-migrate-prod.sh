#!/usr/bin/env bash
# Move the production `trendi` stack and the `asterisk` stack from Docker to Podman TOGETHER. Run as root on the VPS.
#
#   podman-migrate-prod.sh            (no arguments; everything is fixed below)
#
# Why one script for two stacks: they reference each other's networks. `trendi` declares `asterisk_phone` external (the telephone
# shell sits on it) and `asterisk` declares `trendi_default` external (the PBX and bridge sit on it). Each stack's own network also
# has a fixed subnet (172.30.91.0/29 is baked into pjsip.conf and ASTERISK_PEERS) that cannot exist under Docker and Podman at once.
#
# Order: protect SIP -> preload images while everything still runs -> pg_dumpall -> stop trendi, then asterisk (Docker) ->
# copy every mounted named volume -> recreate asterisk_phone in Podman WITH compose's labels (compose refuses an unlabelled
# network) -> start trendi (shell included), then asterisk, through the Podman socket -> wait until healthy.
# Any failure: tear Podman down, recreate the network in Docker with the same labels, start trendi then asterisk in Docker.
# Docker's data (/var/lib/docker) is never modified, so Docker can always take everything back.
set -Eeuo pipefail

V=/opt/trendi/releases/20261108-vps/product/scripts/vps
A=/opt/trendi/releases/20261108-vps/product/scripts/asterisk
CENV=/opt/trendi/shared/compose.env
PENV=/opt/trendi/shared/phone.env
SOCK="unix:///run/podman/podman.sock"
WAIT_TRIES="${WAIT_TRIES:-120}"   # x3s; clamav loads its signature database for a couple of minutes
BK="/root/podman-migration/prod-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BK"; chmod 700 "$BK"

tdc()  { (cd "$V" && docker compose --env-file "$CENV" -f compose.yml --profile public "$@"); }
ptdc() { (cd "$V" && DOCKER_HOST="$SOCK" docker compose --env-file "$CENV" -f compose.yml --profile public "$@"); }
adc()  { (cd "$A" && docker compose --env-file "$PENV" -f compose.yml -f compose.public.yml "$@"); }
padc() { (cd "$A" && DOCKER_HOST="$SOCK" docker compose --env-file "$PENV" -f compose.yml -f compose.public.yml "$@"); }

NETLABELS=(--label com.docker.compose.project=asterisk --label com.docker.compose.network=phone)
PHONE_SUBNET=172.30.91.0/29

# ---- preflight: nothing has been touched yet ------------------------------------------------------------------------------------
systemctl enable --now podman.socket >/dev/null
podman info >/dev/null
for cfg in "tdc config --format json" "adc config --format json"; do
  $cfg | python3 -c '
import sys, json
bad = [n for n, s in json.load(sys.stdin)["services"].items()
       for t in [(s.get("healthcheck") or {}).get("test") or []]
       if t[:1] == ["CMD"] and any(" " in str(a) for a in t[1:])]
if bad: sys.exit("exec-form healthcheck with a space (Podman would split it): " + ", ".join(bad))'
done
# SIP must be carrier-only BEFORE anything is republished by Podman: the jump has to sit in FORWARD, not just DOCKER-USER.
iptables -C FORWARD -p udp -m conntrack --ctstate DNAT --ctorigdstport 5060 -j TRENDI-SIP 2>/dev/null \
  || { echo "!!! FORWARD has no TRENDI-SIP jump; run trendi-sip-firewall.sh (new version) first" >&2; exit 1; }
mapfile -t images < <( { tdc config --images; adc config --images; } | sort -u)
echo "==> backup dir $BK"; echo "    images: ${images[*]}"

# ---- 1. preload images while the live stack is still serving (no downtime cost) ---------------------------------------------------
for img in "${images[@]}"; do
  if docker image inspect "$img" >/dev/null 2>&1; then docker save "$img" | podman load >/dev/null; echo "    loaded $img"
  else echo "    $img not in Docker; Podman will pull it"; fi
done

# ---- 2. consistent logical backup while the database still runs -------------------------------------------------------------------
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | sort > "$BK/containers-before.txt"
docker exec trendi-postgres-1 pg_dumpall -U postgres > "$BK/pg_dumpall.sql"
[[ -s "$BK/pg_dumpall.sql" ]] || { echo "pg_dumpall produced nothing; stopping before any change" >&2; exit 1; }
echo "    pg_dumpall: $(wc -c < "$BK/pg_dumpall.sql") bytes"
mkdir -p "$BK/project-vps" "$BK/project-asterisk"; cp -a "$V/." "$BK/project-vps/"; cp -a "$A/." "$BK/project-asterisk/"
# (two label filters on one command would be ANDed and match nothing, so ask for each project separately)
mapfile -t volumes < <( { docker ps -aq --filter label=com.docker.compose.project=trendi; docker ps -aq --filter label=com.docker.compose.project=asterisk; } \
  | xargs -r docker inspect --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{"\n"}}{{end}}{{end}}' | sort -u | grep -v '^$' || true)
echo "    volumes: ${volumes[*]:-none}"
# Refuse BEFORE anything is stopped: a copy left by an earlier attempt is stale (Docker kept writing) and must be removed by hand.
for v in "${volumes[@]}"; do
  podman volume exists "$v" && { echo "!!! podman volume $v already exists (stale copy?). Remove it with: podman volume rm $v" >&2; exit 1; }
done

# The phone network's addresses are all FIXED now (PBX .2 in pjsip.conf, shell .3 in scripts/vps/compose.yml, bridge .4 in
# scripts/asterisk/compose.yml), so IPAM can no longer hand .2 to whichever container starts first. There is no need to hold the
# shell back: starting the whole trendi stack (shell included) and then asterisk cannot reproduce the 2026-11-17 "Address already
# in use" race. (The old --scale shell=0 dance was removed: re-adding a scaled-to-0 service makes Podman's compose recreate
# trendi-api-1, which the daemon refuses because social uses network_mode: service:api.)
rollback() {
  trap - ERR
  echo "!!! FAILED: putting trendi and asterisk back on Docker" >&2
  padc down --timeout 20 >/dev/null 2>&1 || true
  ptdc down --timeout 20 >/dev/null 2>&1 || true
  podman network rm -f asterisk_phone trendi_default >/dev/null 2>&1 || true
  docker network inspect asterisk_phone >/dev/null 2>&1 || docker network create "${NETLABELS[@]}" --subnet "$PHONE_SUBNET" asterisk_phone >/dev/null 2>&1 || true
  tdc up -d >&2 || true
  adc up -d >&2 || true
  echo "!!! rolled back to Docker. Docker data untouched. Backup: $BK" >&2
}
trap rollback ERR

# ---- 3. stop under Docker: trendi first (asterisk_phone still exists for its external reference), then asterisk -------------------
echo "==> stopping under Docker"
tdc down --timeout 30
adc down --timeout 30

# ---- 4. volumes ---------------------------------------------------------------------------------------------------------------------
for v in "${volumes[@]}"; do
  podman volume exists "$v" && { echo "    podman volume $v already exists; refusing to overwrite" >&2; false; }
  podman volume create "$v" >/dev/null
  cp -a "$(docker volume inspect "$v" --format '{{.Mountpoint}}')/." "$(podman volume inspect "$v" --format '{{.Mountpoint}}')/"
  echo "    volume $v copied ($(du -sh "$(podman volume inspect "$v" --format '{{.Mountpoint}}')" | cut -f1))"
done

# ---- 5. network, then start trendi, then asterisk --------------------------------------------------------------------------------------
docker network inspect asterisk_phone >/dev/null 2>&1 && docker network rm asterisk_phone >/dev/null
podman network create "${NETLABELS[@]}" --subnet "$PHONE_SUBNET" asterisk_phone >/dev/null
echo "==> starting trendi under Podman (shell included; .2/.3/.4 are fixed)"; ptdc up -d
echo "==> starting asterisk under Podman (PBX .2, bridge .4)"; padc up -d

echo "==> waiting for health"
for _ in $(seq 1 "$WAIT_TRIES"); do
  states="$(podman ps -a --format '{{.Status}}' --filter label=com.docker.compose.project=trendi; podman ps -a --format '{{.Status}}' --filter label=com.docker.compose.project=asterisk)"
  if [[ -n "$states" ]] && ! grep -qiE 'starting|unhealthy|exited|created|restarting' <<<"$states"; then ok=1; break; fi
  sleep 3
done
for p in trendi asterisk; do podman ps -a --filter label=com.docker.compose.project=$p --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | cut -c1-120; done
[[ "${ok:-0}" == 1 ]] || { echo "stacks did not become healthy in time" >&2; false; }
trap - ERR
echo "==> trendi and asterisk are running under Podman. Docker's copies are untouched at /var/lib/docker."
