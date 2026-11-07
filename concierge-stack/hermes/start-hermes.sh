#!/usr/bin/env bash
# Starts Hermes Agent (Nous Research, MIT licence) in Docker for the Concierge project.
#
#   ./concierge-stack/hermes/start-hermes.sh          start or restart it
#   ./concierge-stack/hermes/start-hermes.sh --stop   stop and remove the container (its data volume is kept)
#
# Safety: the container listens ONLY on this Mac (127.0.0.1:8642), needs a Bearer key, has memory and CPU limits,
# and can see nothing on this Mac except its own data volume. The xAI key is copied from concierge-stack/.env into the
# volume through stdin, so it never appears on a command line or in output. The key used to call Hermes is created once
# and kept in concierge-stack/hermes/hermes.env (git-ignored, owner-only). Nothing is sent anywhere except to xAI.
#
# Pinned: change IMAGE only on purpose. `stable` is Hermes's release-gate tag; for stricter pinning use a version tag or digest.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
STACK="$(cd "$DIR/.." && pwd)"
IMAGE="${HERMES_IMAGE:-nousresearch/hermes-agent:stable}"
NAME="hermes-concierge"
VOLUME="hermes_concierge_data"
SECRETS="$DIR/hermes.env"
MODEL="${HERMES_MODEL:-grok-4.20-0309-non-reasoning}"
PORT=8642

if [[ "${1:-}" == "--stop" ]]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  echo "Hermes stopped. Its data volume ($VOLUME) is kept."
  exit 0
fi

if ! docker info >/dev/null 2>&1; then echo "Docker is not running. Start Docker Desktop first." >&2; exit 1; fi
if [[ ! -f "$STACK/.env" ]]; then echo "No $STACK/.env. Run ./concierge-stack/set-key.sh first." >&2; exit 1; fi
XAI_KEY="$(grep '^XAI_API_KEY=' "$STACK/.env" | head -1 | cut -d= -f2-)"
if [[ -z "${XAI_KEY// }" ]]; then echo "No XAI_API_KEY in $STACK/.env." >&2; exit 1; fi

if [[ ! -f "$SECRETS" ]]; then
  ( umask 077; printf 'HERMES_API_KEY=%s\n' "$(openssl rand -hex 32)" > "$SECRETS" )
fi
chmod 600 "$SECRETS"
HERMES_KEY="$(grep '^HERMES_API_KEY=' "$SECRETS" | head -1 | cut -d= -f2-)"

docker volume create "$VOLUME" >/dev/null

# Settings go into the data volume through stdin (not the command line).
{
  printf 'XAI_API_KEY=%s\n' "$XAI_KEY"
  printf 'API_SERVER_ENABLED=true\n'
  printf 'API_SERVER_HOST=0.0.0.0\n'
  printf 'API_SERVER_KEY=%s\n' "$HERMES_KEY"
} | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c 'umask 077; cat > /opt/data/.env'
printf 'model:\n  default: %s\n  provider: xai\n' "$MODEL" \
  | docker run --rm -i -v "$VOLUME":/opt/data --entrypoint /bin/sh "$IMAGE" -c 'cat > /opt/data/config.yaml'

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped \
  --memory 3g --cpus 2 \
  -v "$VOLUME":/opt/data \
  -p "127.0.0.1:$PORT:8642" \
  "$IMAGE" gateway run >/dev/null

echo "Waiting for Hermes to answer on 127.0.0.1:$PORT ..."
for _ in $(seq 1 45); do
  if curl -s -m 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" | grep -q '^200$'; then
    echo "Hermes is up (health check passed). Model: $MODEL"
    echo "Try it: ./concierge-stack/hermes/ask-hermes.sh \"Say hello in five words\""
    exit 0
  fi
  sleep 2
done
echo "Hermes did not answer in 90 seconds. Last log lines:" >&2
docker logs --tail 25 "$NAME" 2>&1 | sed 's/\(KEY\|key\|TOKEN\|token\)=[^ ]*/\1=<hidden>/g' >&2
exit 1
