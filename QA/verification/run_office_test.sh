#!/bin/zsh
# Fresh throwaway DB + the OFFICE-branch API + seed + browser test. Never touches the live stack (ports 55432 / 18080).
pkill -f "uvicorn app.main:app --port 18080" 2>/dev/null
docker rm -f cc-office-test cc-dash-test >/dev/null 2>&1
docker run -d --rm --name cc-office-test -e POSTGRES_PASSWORD=test -p 127.0.0.1:55432:5432 pgvector/pgvector:pg16 >/dev/null 2>&1
sleep 5
cd ~/work-staging/concierge-office/api
DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres ADMIN_TOKEN=admin-test-token OUTBOX_ENABLED=false \
PUBLIC_BASE_URL=http://127.0.0.1:18080 PYTHONPATH=$HOME/work-staging/shims \
nohup ~/work-staging/venv-concierge/bin/uvicorn app.main:app --port 18080 > ~/work-staging/office-server.log 2>&1 &
for i in {1..20}; do curl -s http://127.0.0.1:18080/healthz >/dev/null && break; sleep 1; done
~/work-staging/venv-concierge/bin/python ~/work-staging/seed_office.py
node ~/work-staging/office_dashboard_test.cjs > ~/work-staging/office-dash-result.txt 2>&1
echo "exit: $?" >> ~/work-staging/office-dash-result.txt
pkill -f "uvicorn app.main:app --port 18080" 2>/dev/null
docker rm -f cc-office-test >/dev/null 2>&1
echo finished >> ~/work-staging/office-dash-result.txt
