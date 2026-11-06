#!/bin/zsh
# Production-like benchmark. Isolated: its own docker network, its own database, ports 18081 / 18099. Never touches the live stack.
B=~/work-staging/bench
rm -f $B/api-bench.out $B/inside-bench.out $B/run.log
pkill -f "stub_llm.py 18099" 2>/dev/null
docker rm -f ccbench-api ccbench-db >/dev/null 2>&1
docker network rm ccbench >/dev/null 2>&1
docker network create ccbench >/dev/null
nohup python3 $B/stub_llm.py 18099 >/dev/null 2>&1 &
docker run -d --rm --name ccbench-db --network ccbench -e POSTGRES_PASSWORD=bench pgvector/pgvector:pg16 >/dev/null
sleep 7
docker run -d --rm --name ccbench-api --network ccbench -p 127.0.0.1:18081:8000 --add-host host.docker.internal:host-gateway \
  -e DATABASE_URL=postgresql://postgres:bench@ccbench-db:5432/postgres -e ADMIN_TOKEN=bench-token -e OUTBOX_ENABLED=false \
  -e LLM_BASE_URL=http://host.docker.internal:18099/v1 -e LLM_API_KEY=stub -e CHAT_MODEL=stub \
  -e PUBLIC_BASE_URL=http://127.0.0.1:18081 -e CHAT_RATE_PER_MINUTE_IP=1000000 -e CHAT_RATE_PER_DAY_SESSION=1000000 \
  concierge-api:latest >/dev/null
for i in {1..40}; do curl -s http://127.0.0.1:18081/healthz >/dev/null && break; sleep 1; done
echo "image python: $(docker exec ccbench-api python -c 'import sys;print(sys.version.split()[0])'), cores visible: $(docker exec ccbench-api nproc)" > $B/run.log
~/work-staging/venv-concierge/bin/python $B/api_bench.py > $B/api-bench.out 2>&1
docker exec -i ccbench-api python - < $B/inside_bench.py > $B/inside-bench.out 2>&1
docker rm -f ccbench-api ccbench-db >/dev/null 2>&1
docker network rm ccbench >/dev/null 2>&1
pkill -f "stub_llm.py 18099" 2>/dev/null
echo finished >> $B/run.log
