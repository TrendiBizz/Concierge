#!/usr/bin/env bash
# Start the Hermes master on this Mac with the Trendi work mounted.
#
#   ./hermes/runtime/start-master.sh            start (or restart) + install profiles/jobs
#   ./hermes/runtime/start-master.sh --no-install   start only
#   ./hermes/runtime/start-master.sh --status   show the container, profiles and jobs
#   ./hermes/runtime/start-master.sh --stop     stop and remove the container (volume kept)
#
# The container is loopback only. It gets read-only keys and repos, and write access
# only to the two work repos and the report directory. It does NOT get the Concierge
# SSH key, the Docker socket, the Keychain or the rest of $HOME.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
STACK="$REPO/concierge-stack"
IMAGE="${HERMES_IMAGE:-nousresearch/hermes-agent:stable}"
NAME="${HERMES_NAME:-hermes-concierge}"
VOLUME="${HERMES_VOLUME:-hermes_concierge_data}"
SECRETS="$STACK/hermes/hermes.env"
PORT="${HERMES_PORT:-8642}"
DASH_PORT="${HERMES_DASHBOARD_PORT:-9120}"
DASH_USER="${HERMES_DASHBOARD_USER:-jo}"
MODEL="${HERMES_MODEL:-grok-4.20-0309-non-reasoning}"
PKG_MOUNT="$REPO/hermes"

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${1:-}" in
  --stop)
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    say "Stopped $NAME. The volume $VOLUME and all mounted files are kept."
    exit 0
    ;;
  --status)
    docker ps -a --filter "name=^${NAME}$" --format 'container: {{.Names}} {{.Status}}' || true
    curl -s -m 3 -o /dev/null -w 'api health: %{http_code}\n' "http://127.0.0.1:$PORT/health" || true
    docker exec "$NAME" hermes profile list 2>&1 | tail -12 || true
    say ""
    docker exec "$NAME" sh -lc 'for p in trendi-master seo-engine trendi-desk pen-test site-watch workwatch; do echo "== $p =="; hermes -p $p cron list --all 2>/dev/null | grep -E "^  [0-9a-f]{6,}|Name:|Schedule:|Next run:" | head -8; done' 2>&1 || true
    exit 0
    ;;
esac

INSTALL=1
[[ "${1:-}" == "--no-install" ]] && INSTALL=0

command -v docker >/dev/null 2>&1 || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "Docker Desktop is not running."
[[ -f "$STACK/.env" ]] || die "No $STACK/.env; run ./concierge-stack/set-key.sh first."
XAI_KEY="$(grep '^XAI_API_KEY=' "$STACK/.env" | head -1 | cut -d= -f2-)"
[[ -n "${XAI_KEY// }" ]] || die "No XAI_API_KEY in $STACK/.env."

[[ -d "$HOME/OpenBot/Shared/trendi-seo" ]] || die "Missing ~/OpenBot/Shared/trendi-seo"
[[ -d "$HOME/OpenBot/Shared/trendi-site" ]] || die "Missing ~/OpenBot/Shared/trendi-site"
[[ -d "$HOME/OpenBot/Shared/workwatch" ]] || die "Missing ~/OpenBot/Shared/workwatch"
[[ -d "$HOME/jo-brain" ]] || die "Missing ~/jo-brain"
[[ -d "$HOME/.config/trendi" ]] || die "Missing ~/.config/trendi (the mode-600 key copies)"
[[ -d "$PKG_MOUNT" ]] || die "Missing $PKG_MOUNT"
[[ -d "$HOME/.workwatch/reports" ]] || die "Missing ~/.workwatch/reports"

if [[ ! -f "$SECRETS" ]]; then
  ( umask 077; printf 'HERMES_API_KEY=%s\n' "$(openssl rand -hex 32)" > "$SECRETS" )
fi
chmod 600 "$SECRETS"
HERMES_KEY="$(grep '^HERMES_API_KEY=' "$SECRETS" | head -1 | cut -d= -f2-)"
[[ -n "${HERMES_KEY// }" ]] || die "No HERMES_API_KEY in $SECRETS"

# Dashboard login. Generated once, kept in the mode-600 secrets file. Change it there
# and re-run this script to rotate.
if ! grep -q '^DASHBOARD_USER=' "$SECRETS"; then
  printf 'DASHBOARD_USER=%s\n' "$DASH_USER" >> "$SECRETS"
fi
if ! grep -q '^DASHBOARD_PASSWORD=' "$SECRETS"; then
  printf 'DASHBOARD_PASSWORD=%s\n' "$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)" >> "$SECRETS"
fi
if ! grep -q '^DASHBOARD_SECRET=' "$SECRETS"; then
  printf 'DASHBOARD_SECRET=%s\n' "$(openssl rand -base64 32)" >> "$SECRETS"
fi
chmod 600 "$SECRETS"
DASH_USER="$(grep '^DASHBOARD_USER=' "$SECRETS" | head -1 | cut -d= -f2-)"
DASH_PASS="$(grep '^DASHBOARD_PASSWORD=' "$SECRETS" | head -1 | cut -d= -f2-)"
DASH_SECRET="$(grep '^DASHBOARD_SECRET=' "$SECRETS" | head -1 | cut -d= -f2-)"
[[ -n "${DASH_USER// }" && -n "${DASH_PASS// }" && -n "${DASH_SECRET// }" ]] || die "Dashboard credentials are empty in $SECRETS"

docker volume create "$VOLUME" >/dev/null

# Write the xAI key and API-server key into the volume through stdin (never argv).
{
  printf 'XAI_API_KEY=%s\n' "$XAI_KEY"
  printf 'API_SERVER_ENABLED=true\n'
  printf 'API_SERVER_HOST=0.0.0.0\n'
  printf 'API_SERVER_KEY=%s\n' "$HERMES_KEY"
} | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c \
      'umask 077; cat > /opt/data/.env'
printf 'model:\n  default: %s\n  provider: xai\n' "$MODEL" \
  | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c \
      'cat > /opt/data/config.yaml'

docker rm -f "$NAME" >/dev/null 2>&1 || true

say "Starting $NAME with the Trendi work mounted ..."
docker run -d --name "$NAME" --restart unless-stopped \
  --memory 4g --cpus 2 --pids-limit 512 \
  --security-opt no-new-privileges:true \
  -e HOME=/opt/data -e TZ=Pacific/Auckland \
  -e HERMES_DASHBOARD=1 \
  -e HERMES_DASHBOARD_HOST=0.0.0.0 \
  -e HERMES_DASHBOARD_PORT=9120 \
  -e HERMES_DASHBOARD_BASIC_AUTH_USERNAME="$DASH_USER" \
  -e HERMES_DASHBOARD_BASIC_AUTH_PASSWORD="$DASH_PASS" \
  -e HERMES_DASHBOARD_BASIC_AUTH_SECRET="$DASH_SECRET" \
  -p "127.0.0.1:$PORT:8642" \
  -p "127.0.0.1:$DASH_PORT:9120" \
  -v "$VOLUME":/opt/data \
  -v "$HOME/OpenBot/Shared/trendi-seo:/opt/data/OpenBot/Shared/trendi-seo" \
  -v "$HOME/OpenBot/Shared/trendi-site:/opt/data/OpenBot/Shared/trendi-site" \
  -v "$HOME/OpenBot/Shared/workwatch:/opt/data/OpenBot/Shared/workwatch:ro" \
  -v "$HOME/jo-brain:/opt/data/jo-brain:ro" \
  -v "$HOME/.workwatch/reports:/opt/data/.workwatch/reports" \
  -v "$HOME/.config/trendi:/opt/data/.config/trendi:ro" \
  -v "$HOME/.config/trendi-seo:/opt/data/.config/trendi-seo:ro" \
  -v "$PKG_MOUNT:/opt/data/work/hermes:ro" \
  "$IMAGE" gateway run >/dev/null

say "Waiting for the Hermes API on 127.0.0.1:$PORT ..."
for _ in $(seq 1 60); do
  code="$(curl -s -m 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)"
  if [[ "$code" == "200" ]]; then
    say "Hermes is up (health $code). Model: $MODEL"
    break
  fi
  sleep 2
done
if [[ "${code:-}" != "200" ]]; then
  docker logs --tail 30 "$NAME" 2>&1 | sed 's/\(KEY\|key\|TOKEN\|token\)=[^ ]*/\1=<hidden>/g' >&2
  die "Hermes did not answer in 120 seconds."
fi

say "Waiting for the Hermes dashboard on 127.0.0.1:$DASH_PORT ..."
dash_code=""
for _ in $(seq 1 30); do
  dash_code="$(curl -s -L -m 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$DASH_PORT/" || true)"
  [[ "$dash_code" == "200" ]] && break
  sleep 2
done
if [[ "$dash_code" != "200" ]]; then
  docker logs --tail 30 "$NAME" 2>&1 | sed 's/\(KEY\|key\|TOKEN\|token\|PASSWORD\|password\)=[^ ]*/\1=<hidden>/g' >&2
  die "Dashboard did not answer on 127.0.0.1:$DASH_PORT."
fi
say "Hermes dashboard: http://127.0.0.1:$DASH_PORT  (user: $DASH_USER)"
say "Dashboard password: $SECRETS (mode 600; change DASHBOARD_PASSWORD there and re-run)"

# One Linux venv for the trendi-seo scripts. The macOS .venv cannot run in Linux.
say "Checking the trendi-seo Python environment ..."
docker exec "$NAME" sh -lc 'mkdir -p /Users && ln -sfn /opt/data /Users/jo && mkdir -p /opt/data/.workwatch/reports/hermes && chmod -R a+rwX /opt/data/.workwatch/reports/hermes && ls -ld /Users/jo'
docker exec "$NAME" sh -lc '
  if [ ! -x /opt/data/venvs/trendi-seo/bin/python ]; then
    python3 -m venv /opt/data/venvs/trendi-seo
    /opt/data/venvs/trendi-seo/bin/pip install --quiet --no-cache-dir \
      --disable-pip-version-check \
      requests google-auth google-auth-oauthlib beautifulsoup4 lxml
  fi
  /opt/data/venvs/trendi-seo/bin/python -c "import requests, google.auth, bs4, lxml; print(\"venv ok\")"
'
docker exec "$NAME" sh -lc '
  if [ ! -x /opt/data/venvs/hermes-tools/bin/python ]; then
    python3 -m venv /opt/data/venvs/hermes-tools
    /opt/data/venvs/hermes-tools/bin/pip install --quiet --no-cache-dir \
      --disable-pip-version-check pyyaml
  fi
  /opt/data/venvs/hermes-tools/bin/python -c "import yaml; print(\"installer venv ok\")"
'

if [[ "$INSTALL" == "1" ]]; then
  say "Installing profiles and schedules ..."
  docker exec "$NAME" /opt/data/venvs/hermes-tools/bin/python \
    /opt/data/work/hermes/install.py --apply
  say ""
  say "Next:"
  say "  ./hermes/runtime/start-master.sh --status"
  say "  open ~/.workwatch/reports/hermes/trendi-master/latest.md"
fi

say ""
say "Image: $IMAGE"
docker image inspect "$IMAGE" --format 'Digest: {{index .RepoDigests 0}}' 2>/dev/null || true
