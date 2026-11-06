#!/bin/zsh
# Same benchmark, but with the embedding model limited to ONE thread per call (patched file mounted read-only into the
# benchmark container only; the repository and the live stack are untouched).
B=~/work-staging/bench
rm -f $B/api-bench-t1.out $B/run-t1.log
pkill -f "stub_llm.py 18099" 2>/dev/null
docker rm -f ccbench-api ccbench-db >/dev/null 2>&1
docker network rm ccbench >/dev/null 2>&1
docker network create ccbench >/dev/null
nohup python3 $B/stub_llm.py 18099 >/dev/null 2>&1 &
docker run -d --rm --name ccbench-db --network ccbench -e POSTGRES_PASSWORD=bench pgvector/pgvector:pg16 >/dev/null
sleep 7
docker run -d --rm --name ccbench-api --network ccbench -p 127.0.0.1:18081:8000 --add-host host.docker.internal:host-gateway \
  -v $B/embeddings_t1.py:/srv/app/embeddings.py:ro \
  -e DATABASE_URL=postgresql://postgres:bench@ccbench-db:5432/postgres -e ADMIN_TOKEN=bench-token -e OUTBOX_ENABLED=false \
  -e LLM_BASE_URL=http://host.docker.internal:18099/v1 -e LLM_API_KEY=stub -e CHAT_MODEL=stub \
  -e PUBLIC_BASE_URL=http://127.0.0.1:18081 -e CHAT_RATE_PER_MINUTE_IP=1000000 -e CHAT_RATE_PER_DAY_SESSION=1000000 \
  concierge-api:latest >/dev/null
for i in {1..40}; do curl -s http://127.0.0.1:18081/healthz >/dev/null && break; sleep 1; done
~/work-staging/venv-concierge/bin/python $B/api_bench.py > $B/api-bench-t1.out 2>&1
docker rm -f ccbench-api ccbench-db >/dev/null 2>&1
docker network rm ccbench >/dev/null 2>&1
pkill -f "stub_llm.py 18099" 2>/dev/null
echo finished > $B/run-t1.log
