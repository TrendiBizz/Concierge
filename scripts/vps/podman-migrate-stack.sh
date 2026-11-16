#!/usr/bin/env bash
# Move ONE compose stack from Docker to Podman (rootful), with a backup first and an automatic rollback.
# Run as root on the VPS, from the stack's compose directory's parent or with the directory given.
#
#   podman-migrate-stack.sh COMPOSE_DIR [--pg SERVICE:USER] [--profile NAME]...
#
# Steps: record state -> pg_dumpall (if --pg) -> copy compose files -> `docker compose down` (never -v) ->
# copy each named volume into a Podman volume of the same name -> `docker save | podman load` each image ->
# `docker compose up -d` through the Podman socket -> wait until nothing is starting/unhealthy.
# If the stack does not come up, it is torn down under Podman and started again under Docker.
# Docker's data (/var/lib/docker) is never modified, so Docker can always take the stack back.
#
# Why volumes are copied with cp -a and not tar-in-a-container: the stack is stopped, root owns both stores, and
# cp -a keeps ownership, modes and sparse files exactly. A running database must never be copied this way.
# -E: without it the ERR trap does not fire for a failure inside a function (pdc/dc), and the rollback silently never ran.
set -Eeuo pipefail

dir="${1:?usage: podman-migrate-stack.sh COMPOSE_DIR [--pg SERVICE:USER] [--profile NAME]...}"; shift
pgs=(); profiles=(); envf=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pg) pgs+=("${2:?--pg needs SERVICE:USER}"); shift 2 ;;   # repeatable: one dump per database service
    --env-file) envf=(--env-file "${2:?--env-file needs a path}"); shift 2 ;;
    --profile) profiles+=(--profile "${2:?--profile needs a name}"); shift 2 ;;
    *) echo "unknown option $1" >&2; exit 1 ;;
  esac
done
cd "$dir"
COMPOSE_FILE_ARG=()
for f in compose.yml compose.yaml compose.json docker-compose.yml docker-compose.yaml; do [[ -f $f ]] && { COMPOSE_FILE_ARG=(-f "$f"); break; }; done
[[ ${#COMPOSE_FILE_ARG[@]} -gt 0 ]] || { echo "no compose file in $dir" >&2; exit 1; }

WAIT_TRIES="${WAIT_TRIES:-60}"   # x3s
PODMAN_SOCK="unix:///run/podman/podman.sock"
dc()  { docker compose ${envf[@]+"${envf[@]}"} "${COMPOSE_FILE_ARG[@]}" ${profiles[@]+"${profiles[@]}"} "$@"; }
pdc() { DOCKER_HOST="$PODMAN_SOCK" docker compose ${envf[@]+"${envf[@]}"} "${COMPOSE_FILE_ARG[@]}" ${profiles[@]+"${profiles[@]}"} "$@"; }

# Refuse before changing anything: Podman's compat API splits an exec-form healthcheck argument on spaces, so
# `test: [CMD, python, -c, "import x; ..."]` runs `python -c import` and is unhealthy forever (found 2026-11-17).
# Write such checks as [CMD-SHELL, "..."] first.
dc config --format json | python3 -c '
import sys, json
bad = [n for n, s in json.load(sys.stdin)["services"].items()
       for t in [(s.get("healthcheck") or {}).get("test") or []]
       if t[:1] == ["CMD"] and any(" " in str(a) for a in t[1:])]
if bad:
    sys.exit("exec-form healthcheck with a space in an argument (Podman would split it): " + ", ".join(bad) + ". Use CMD-SHELL.")'
project="$(dc config --format json | python3 -c 'import sys,json;print(json.load(sys.stdin)["name"])')"
BK="/root/podman-migration/$project-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BK"; chmod 700 "$BK"
echo "==> $project: backup dir $BK"

systemctl enable --now podman.socket >/dev/null
podman info >/dev/null

# 1. what is running now, and the files that define it (env files hold secrets: the dir is root-only)
docker ps -a --filter "label=com.docker.compose.project=$project" \
  --format '{{.Names}}\t{{.Image}}\t{{.Status}}' > "$BK/containers-before.txt"
cp -a "$dir/." "$BK/project/"
mapfile -t images < <(dc config --images | sort -u)
# Volumes come from what the containers actually mount, not from compose labels: an `external: true` volume carries no label.
mapfile -t volumes < <(docker ps -aq --filter "label=com.docker.compose.project=$project" \
  | xargs -r docker inspect --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{"\n"}}{{end}}{{end}}' | sort -u | grep -v '^$' || true)
echo "    images: ${images[*]}"; echo "    volumes: ${volumes[*]:-none}"

# 2. a logical dump while the database still runs: the one backup that is consistent by construction
for pg in ${pgs[@]+"${pgs[@]}"}; do
  svc="${pg%%:*}"; user="${pg##*:}"
  dc exec -T "$svc" pg_dumpall -U "$user" > "$BK/pg_dumpall-$svc.sql"
  [[ -s "$BK/pg_dumpall-$svc.sql" ]] || { echo "pg_dumpall of $svc produced nothing; stopping before any change" >&2; exit 1; }
  echo "    pg_dumpall $svc: $(wc -c < "$BK/pg_dumpall-$svc.sql") bytes"
done

rollback() {
  echo "!!! FAILED: putting $project back on Docker" >&2
  pdc down --timeout 20 >/dev/null 2>&1 || true
  dc up -d >&2 || true
  echo "!!! rolled back. Docker data untouched. Backup: $BK" >&2
}
trap rollback ERR

# 3. stop under Docker (no -v: volumes stay)
echo "==> stopping under Docker"
dc down --timeout 30

# 4. volumes, then images
for v in ${volumes[@]+"${volumes[@]}"}; do
  podman volume exists "$v" && { echo "    podman volume $v already exists; refusing to overwrite" >&2; false; }
  podman volume create "$v" >/dev/null
  src="$(docker volume inspect "$v" --format '{{.Mountpoint}}')"
  dst="$(podman volume inspect "$v" --format '{{.Mountpoint}}')"
  cp -a "$src/." "$dst/"
  echo "    volume $v: $(du -sh "$src" | cut -f1) -> $(du -sh "$dst" | cut -f1)"
done
for img in "${images[@]}"; do
  if docker image inspect "$img" >/dev/null 2>&1; then docker save "$img" | podman load >/dev/null && echo "    image $img loaded"
  else echo "    image $img not in Docker; Podman will pull it"; fi
done

# 5. start under Podman through the Docker-compatible socket, then wait for health
# Found 2026-11-17: Podman's DNS (aardvark-dns) listens on each bridge's gateway address, so a container's lookup is a packet INTO
# the host, which ufw's default-deny drops ("Temporary failure in name resolution", the app restarts forever). Docker's DNS lives in
# the daemon and never needed this. Allow only DNS, only on Podman's bridges.
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
  ufw status | grep -q 'on podman+' || ufw allow in on 'podman+' to any port 53 comment 'podman container DNS (aardvark-dns)' >/dev/null
fi
echo "==> starting under Podman"
pdc up -d
for _ in $(seq 1 "$WAIT_TRIES"); do
  states="$(podman ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Status}}')"
  if [[ -n "$states" ]] && ! grep -qiE 'starting|unhealthy|exited|created' <<<"$states"; then ok=1; break; fi
  sleep 3
done
podman ps -a --filter "label=com.docker.compose.project=$project" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
[[ "${ok:-0}" == 1 ]] || { echo "stack did not become healthy in time" >&2; false; }
trap - ERR
echo "==> $project is running under Podman. Docker copy of the volumes is untouched at /var/lib/docker."
echo "    Roll back later with: (cd $dir && DOCKER_HOST=$PODMAN_SOCK docker compose down && docker compose up -d)"
