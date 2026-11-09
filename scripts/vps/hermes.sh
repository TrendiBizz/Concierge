#!/usr/bin/env bash
# Control Hermes on the VPS. Run as root on the VPS.
#
#   hermes.sh start  [--tenant SLUG] [--mode internal|customer]
#   hermes.sh stop   [--tenant SLUG]            (the data volume is kept)
#   hermes.sh status [--tenant SLUG]
#   hermes.sh ask    [--tenant SLUG] "question"
#
# The Mac script (concierge-stack/hermes/start-hermes.sh) is the proven recipe; this follows it, with these changes:
#   * secrets come from /opt/trendi/shared (root-only) and are never printed or put on a command line;
#   * one container + volume + loopback port per business, so memory and credentials are never shared across customers;
#   * `--mode customer` REFUSES to start unless an operator-verified toolset file exists. The installed Hermes build's
#     tool configuration has not been confirmed, so this script does not guess config keys: broad tools (terminal,
#     files, browser, cron, delegation) must be restricted first (framework §8).
set -euo pipefail

SHARED=/opt/trendi/shared
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$HERE/compose.hermes.yml"
XAI_SOURCE="${HERMES_XAI_ENV_FILE:-$SHARED/api.env}"
MODEL="${HERMES_MODEL:-grok-4.20-0309-non-reasoning}"

cmd="${1:-}"; [[ -n "$cmd" ]] || { sed -n 2,9p "$0" >&2; exit 1; }
shift || true
tenant=pilot; mode=internal; question=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tenant) tenant="${2:?--tenant needs a value}"; shift 2 ;;
    --mode)   mode="${2:?--mode needs a value}"; shift 2 ;;
    *)        question="$1"; shift ;;
  esac
done

[[ "$tenant" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || { echo "Tenant must be 1-32 lowercase letters, digits or hyphens." >&2; exit 1; }
[[ "$mode" == internal || "$mode" == customer ]] || { echo "--mode must be internal or customer." >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo "Run as root on the VPS." >&2; exit 1; }
[[ "${HERMES_SH_SKIP_DOCKER_CHECK:-}" == 1 ]] || command -v docker >/dev/null || { echo "docker is not installed." >&2; exit 1; }

NAME="hermes-$tenant"
VOLUME="hermes_${tenant}_data"
KEYDIR="$SHARED/hermes"
KEYFILE="$KEYDIR/$tenant.env"

# Deterministic per-tenant loopback port: 8642 for "pilot", otherwise a stable port in 8650-8899.
port_for() {
  if [[ "$1" == pilot ]]; then echo 8642; return; fi
  echo $(( 8650 + $(printf '%s' "$1" | cksum | cut -d' ' -f1) % 250 ))
}
PORT="$(port_for "$tenant")"
compose() { HERMES_TENANT="$tenant" HERMES_PORT="$PORT" docker compose -f "$COMPOSE_FILE" "$@"; }
read_key() { grep -m1 '^HERMES_API_KEY=' "$KEYFILE" | cut -d= -f2-; }

case "$cmd" in
  start)
    TOOLSETS="$KEYDIR/$tenant.toolsets.yaml"
    # Checked first, before anything is read or created: customer content must never reach an unrestricted agent.
    if [[ "$mode" == customer && ! -s "$TOOLSETS" ]]; then
      echo "Refusing to start '$tenant' in customer mode: $TOOLSETS is missing." >&2
      echo "Restrict Hermes's tools first (no terminal, file, browser, cron or delegation) using the keys the installed" >&2
      echo "build actually supports, save that YAML there, then start again. Nothing was created." >&2
      exit 2
    fi
    docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
    [[ -f "$XAI_SOURCE" ]] || { echo "No $XAI_SOURCE (set HERMES_XAI_ENV_FILE)." >&2; exit 1; }
    XAI_KEY="$(grep -m1 '^XAI_API_KEY=' "$XAI_SOURCE" | cut -d= -f2- || true)"
    [[ -n "${XAI_KEY// }" ]] || { echo "No XAI_API_KEY in $XAI_SOURCE." >&2; exit 1; }
    install -d -m 700 "$SHARED" "$KEYDIR"
    if [[ ! -s "$KEYFILE" ]]; then ( umask 077; printf 'HERMES_API_KEY=%s\n' "$(openssl rand -hex 32)" > "$KEYFILE" ); fi
    chmod 600 "$KEYFILE"
    IMAGE="${HERMES_IMAGE:-nousresearch/hermes-agent:stable}"
    docker volume create "$VOLUME" >/dev/null
    # Settings reach the volume through stdin, never a command line or log.
    {
      printf 'XAI_API_KEY=%s\n' "$XAI_KEY"
      printf 'API_SERVER_ENABLED=true\n'
      printf 'API_SERVER_HOST=0.0.0.0\n'
      printf 'API_SERVER_KEY=%s\n' "$(read_key)"
    } | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c 'umask 077; cat > /opt/data/.env'
    {
      printf 'model:\n  default: %s\n  provider: xai\n' "$MODEL"
      if [[ -s "$TOOLSETS" ]]; then cat "$TOOLSETS"; fi
    } | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c 'cat > /opt/data/config.yaml'
    unset XAI_KEY
    compose up -d
    echo "Hermes '$tenant' ($mode) starting on 127.0.0.1:$PORT. Waiting for it to answer..."
    for _ in $(seq 1 30); do
      if curl -fsS -m 3 -o /dev/null -H "Authorization: Bearer $(read_key)" "http://127.0.0.1:$PORT/v1/models" 2>/dev/null; then
        echo "Hermes answered."; exit 0
      fi
      sleep 2
    done
    echo "Hermes did not answer within 60 s. Check: docker logs $NAME" >&2; exit 1 ;;
  stop)
    compose down
    echo "Hermes '$tenant' stopped. Volume $VOLUME is kept." ;;
  status)
    docker inspect -f '{{.Name}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}}' "$NAME" 2>/dev/null \
      || echo "$NAME is not running."
    docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' "$NAME" 2>/dev/null || true ;;
  ask)
    [[ -n "$question" ]] || { echo 'Usage: hermes.sh ask [--tenant SLUG] "question"' >&2; exit 1; }
    [[ -s "$KEYFILE" ]] || { echo "No key for '$tenant'. Run: hermes.sh start --tenant $tenant" >&2; exit 1; }
    BODY="$(PROMPT="$question" python3 -c 'import json,os;print(json.dumps({"model":"hermes-agent","messages":[{"role":"user","content":os.environ["PROMPT"]}]}))')"
    curl -sS -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" -H "Authorization: Bearer $(read_key)" -H "Content-Type: application/json" -d "$BODY" \
      | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["choices"][0]["message"]["content"])' ;;
  *) echo "Unknown command: $cmd" >&2; exit 1 ;;
esac
