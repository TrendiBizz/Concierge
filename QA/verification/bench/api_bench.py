"""API benchmark against a PRODUCTION-LIKE container (same image, Python 3.12, one uvicorn worker, real embedding model)
on a throwaway database, with an instant stub LLM. Measures only the work our code does."""
import asyncio
import statistics
import subprocess
import threading
import time

import httpx

BASE = "http://127.0.0.1:18081"
ADMIN = {"X-Admin-Token": "bench-token"}
PARAS = [
    f"Section {i}. Our plumbing company services Auckland. We repair burst pipes, replace hot water cylinders, install heat pumps "
    f"and renovate bathrooms. Emergency call-outs are available. Topic number {i} covers pricing, booking, warranties and areas served. "
    f"Call or message us for a quote and we will confirm a time that suits you. " * 3
    for i in range(40)
]


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p / 100))]


def summarize(label, ms, wall=None, errors=0):
    line = f"{label:<46} n={len(ms):<5} p50={pct(ms, 50):7.1f}ms  p95={pct(ms, 95):7.1f}ms  p99={pct(ms, 99):7.1f}ms  max={max(ms):7.1f}ms"
    if wall:
        line += f"  throughput={len(ms) / wall:7.0f}/s"
    if errors:
        line += f"  ERRORS={errors}"
    print(line)


def cpu_sampler(stop, out):
    while not stop.is_set():
        r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", "ccbench-api"], capture_output=True, text=True)
        try:
            out.append(float(r.stdout.strip().rstrip("%")))
        except ValueError:
            pass
        time.sleep(0.2)


async def timed(client, method, url, **kw):
    t = time.perf_counter()
    r = await client.request(method, url, **kw)
    return (time.perf_counter() - t) * 1000, r.status_code


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=60, limits=httpx.Limits(max_connections=200)) as c:
        r = await c.post("/admin/tenants", headers=ADMIN, json={"name": "Bench Plumbing", "slug": "bench"})
        key = r.json()["public_key"]
        t = time.perf_counter()
        for i in range(0, 40, 10):
            await c.post("/admin/tenants/bench/ingest-text", headers=ADMIN, json={"label": f"doc{i}", "title": f"Doc {i}", "text": "\n\n".join(PARAS[i:i + 10])})
        n_chunks = (await c.get("/admin/tenants/bench", headers=ADMIN)).json()["chunk_count"]
        ing = time.perf_counter() - t
        print(f"Ingest: {n_chunks} chunks embedded and stored in {ing:.1f}s  ({n_chunks / ing:.1f} chunks/s)\n")

        print("== One visitor at a time (latency)")
        ms = [(await timed(c, "GET", "/healthz"))[0] for _ in range(300)]
        summarize("GET /healthz (DB round trip)", ms)
        ms = [(await timed(c, "GET", f"/api/v1/widget-config?key={key}"))[0] for _ in range(300)]
        summarize("GET /api/v1/widget-config", ms)
        ms = []
        for i in range(60):
            m, code = await timed(c, "POST", "/api/v1/chat", json={"key": key, "session_id": f"bench-serial-{i:04d}", "message": "What do you charge for a hot water cylinder?"})
            assert code == 200, code
            ms.append(m)
        summarize("POST /api/v1/chat (LLM instant)", ms)

        for label, method, url, kw, total, conc in [
            ("GET /api/v1/widget-config, 50 at once", "GET", f"/api/v1/widget-config?key={key}", {}, 4000, 50),
            ("POST /api/v1/chat, 20 at once (LLM instant)", "POST", "/api/v1/chat", "chat", 400, 20),
        ]:
            print(f"\n== {label}")
            sem = asyncio.Semaphore(conc)
            lat, errs = [], 0
            stop, cpu = threading.Event(), []
            th = threading.Thread(target=cpu_sampler, args=(stop, cpu)); th.start()

            async def one(i):
                nonlocal errs
                async with sem:
                    body = {"key": key, "session_id": f"bench-load-{label[:4]}-{i:06d}", "message": f"Question {i}: do you service my area and what are your hours?"} if kw == "chat" else None
                    m, code = await timed(c, method, url, **({"json": body} if body else {}))
                    if code != 200:
                        errs += 1
                    lat.append(m)
            t0 = time.perf_counter()
            await asyncio.gather(*(one(i) for i in range(total)))
            wall = time.perf_counter() - t0
            stop.set(); th.join()
            summarize(label.split(",")[0], lat, wall, errs)
            if cpu:
                print(f"   container CPU during the run: avg {statistics.mean(cpu):.0f}%  peak {max(cpu):.0f}%  (100% = one core; one worker can use at most one)")

asyncio.run(main())
