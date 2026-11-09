#!/usr/bin/env bash
# Control Hermes on the VPS. Run as root on the VPS.
#
#   hermes.sh start  [--tenant SLUG] [--mode internal|customer]
#   hermes.sh stop   [--tenant SLUG]            (the data volume is kept)
#   hermes.sh status [--tenant SLUG]
#   hermes.sh ask    [--tenant SLUG] "question"
#   hermes.sh gateway-start   [--tenant SLUG]   build and start the Hermes gateway (loopback :4420)
#   hermes.sh gateway-stop | gateway-status
#   hermes.sh gateway-connect --yes             append the Concierge-side switch to api.env (does NOT restart anything)
#   hermes.sh gateway-run TENANT_UUID CASE_UUID   one explicit run on one case (shadow mode only validates; nothing sends)
#
# The Mac script (concierge-stack/hermes/start-hermes.sh) is the proven recipe; this follows it, with these changes:
#   * secrets come from /opt/trendi/shared (root-only) and are never printed or put on a command line;
#   * one container + volume + loopback port per business, so memory and credentials are never shared across customers;
#   * `--mode customer` REFUSES to start unless an operator-verified toolset file exists. The installed Hermes build's
#     tool configuration has not been confirmed, so this script does not guess config keys: broad tools (terminal,
#     files, browser, cron, delegation) must be restricted first (framework §8).
set -euo pipefail

SHARED="${HERMES_SHARED_DIR:-/opt/trendi/shared}"
HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$HERE/compose.hermes.yml"
XAI_SOURCE="${HERMES_XAI_ENV_FILE:-$SHARED/api.env}"
MODEL="${HERMES_MODEL:-grok-4.20-0309-non-reasoning}"

cmd="${1:-}"; [[ -n "$cmd" ]] || { sed -n 2,9p "$0" >&2; exit 1; }
shift || true
tenant=pilot; mode=internal; question=""; extra=""; yes=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tenant) tenant="${2:?--tenant needs a value}"; shift 2 ;;
    --mode)   mode="${2:?--mode needs a value}"; shift 2 ;;
    --yes)    yes=1; shift ;;
    *)        if [[ -z "$question" ]]; then question="$1"; else extra="$1"; fi; shift ;;
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
GWFILE="$KEYDIR/gateway.env"
GWCOMPOSE="$HERE/compose.hermes-gateway.yml"
gateway_value() { grep -m1 "^$1=" "$GWFILE" | cut -d= -f2-; }

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
  gateway-start)
    docker info >/dev/null 2>&1 || { echo "Docker is not running." >&2; exit 1; }
    [[ -s "$KEYFILE" ]] || { echo "Start Hermes first: hermes.sh start --tenant $tenant" >&2; exit 1; }
    install -d -m 700 "$SHARED" "$KEYDIR"
    if [[ ! -s "$GWFILE" ]]; then
      # Three DISTINCT keys; the gateway refuses to start otherwise. Written owner-only, never printed.
      ( umask 077
        {
          printf 'HERMES_CAPABILITY_SECRET=%s\n' "$(openssl rand -hex 32)"
          printf 'HERMES_MINT_KEY=%s\n' "$(openssl rand -hex 32)"
          printf 'HERMES_CONCIERGE_KEY=%s\n' "$(openssl rand -hex 32)"
        } > "$GWFILE" )
    fi
    chmod 600 "$GWFILE"
    # Hermes's own key and address follow the tenant chosen here (one Hermes per gateway for now).
    { grep -v -e '^HERMES_API_KEY=' -e '^HERMES_BASE_URL=' -e '^CONCIERGE_BASE_URL=' "$GWFILE" || true
      printf 'HERMES_API_KEY=%s\n' "$(read_key)"
      printf 'HERMES_BASE_URL=http://127.0.0.1:%s\n' "$PORT"
      printf 'CONCIERGE_BASE_URL=%s\n' "${CONCIERGE_BASE_URL:-http://127.0.0.1:8000}"
    } > "$GWFILE.new" && chmod 600 "$GWFILE.new" && mv "$GWFILE.new" "$GWFILE"
    docker compose -f "$GWCOMPOSE" up -d --build
    echo "Hermes gateway starting on 127.0.0.1:4420. Concierge refuses it (404) until: hermes.sh gateway-connect --yes" ;;
  gateway-stop)
    docker compose -f "$GWCOMPOSE" down
    echo "Hermes gateway stopped." ;;
  gateway-status)
    docker inspect -f '{{.Name}} state={{.State.Status}} restarts={{.RestartCount}}' hermes-gateway 2>/dev/null || echo "hermes-gateway is not running."
    curl -fsS -m 3 http://127.0.0.1:4420/healthz >/dev/null 2>&1 && echo "healthz ok" || echo "healthz not answering" ;;
  gateway-connect)
    [[ -s "$GWFILE" ]] || { echo "Run gateway-start first." >&2; exit 1; }
    API_ENV="${HERMES_API_ENV_FILE:-$SHARED/api.env}"
    [[ -f "$API_ENV" ]] || { echo "No $API_ENV." >&2; exit 1; }
    if [[ "$yes" != 1 ]]; then
      echo "This would append HERMES_GATEWAY_ENABLED=true and HERMES_GATEWAY_KEY=<the gateway's Concierge key> to $API_ENV." >&2
      echo "It does not restart anything: recreate api and social together afterwards. Re-run with --yes to proceed." >&2
      exit 2
    fi
    if grep -q '^HERMES_GATEWAY_KEY=' "$API_ENV"; then echo "$API_ENV already has HERMES_GATEWAY_KEY; nothing changed."; exit 0; fi
    { printf '\nHERMES_GATEWAY_ENABLED=true\n'; printf 'HERMES_GATEWAY_KEY=%s\n' "$(gateway_value HERMES_CONCIERGE_KEY)"; } >> "$API_ENV"
    echo "Appended to $API_ENV. Recreate api and social together to apply; autonomy stays 'shadow' until set per business." ;;
  gateway-run)
    [[ -s "$GWFILE" ]] || { echo "Run gateway-start first." >&2; exit 1; }
    uuid='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    [[ "$question" =~ $uuid && "$extra" =~ $uuid ]] || { echo "Usage: hermes.sh gateway-run TENANT_UUID CASE_UUID" >&2; exit 1; }
    RUN_ID="manual-$(date +%Y%m%d%H%M%S)-$$"
    BODY="$(python3 -c 'import json,sys;print(json.dumps({"tenant_id":sys.argv[1],"case_id":sys.argv[2],"run_id":sys.argv[3]}))' "$question" "$extra" "$RUN_ID")"
    curl -sS -m 150 http://127.0.0.1:4420/v1/runs -H "Authorization: Bearer $(gateway_value HERMES_MINT_KEY)" -H 'Content-Type: application/json' -d "$BODY" | python3 -m json.tool ;;
  *) echo "Unknown command: $cmd" >&2; exit 1 ;;
esac
