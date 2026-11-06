#!/bin/zsh
# Safe, isolated browser test. No production database, network messaging, or shared port.
set -e
ROOT=/Users/jo/work-staging/concierge-integration
cd "$ROOT"
if docker ps --format '{{.Names}}' | grep -qx cc-email-browser; then
  echo "Refusing to reuse an existing test container."
  exit 1
fi
if lsof -n -iTCP:18082 -sTCP:LISTEN | grep -q LISTEN; then
  echo "Refusing to occupy port 18082."
  exit 1
fi
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then kill "$server_pid" >/dev/null 2>&1 || :; fi
  docker rm -f cc-email-browser >/dev/null 2>&1 || :
}
trap cleanup EXIT
docker run -d --rm --name cc-email-browser -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 pgvector/pgvector:pg16 >/dev/null
for i in {1..25}; do
  docker exec cc-email-browser pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
cd "$ROOT/api"
DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres \
ADMIN_TOKEN=admin-test-token OUTBOX_ENABLED=false EMAIL_DRAFTS_ENABLED=true \
PUBLIC_BASE_URL=http://127.0.0.1:18082 \
PYTHONPATH="$ROOT/QA/verification/shims" \
/Users/jo/work-staging/venv-concierge/bin/uvicorn app.main:app --host 127.0.0.1 --port 18082 \
  > /tmp/concierge-email-browser-server.log 2>&1 &
server_pid=$!
for i in {1..25}; do
  curl -fsS http://127.0.0.1:18082/healthz >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:18082/healthz >/dev/null
/Users/jo/work-staging/venv-concierge/bin/python "$ROOT/QA/verification/seed_office.py"
node "$ROOT/QA/verification/email_dashboard_test.cjs"
