"""Differential test: the real Rust server (concierge-server) and the real Python API answer the SAME requests over the SAME PostgreSQL.

Local run (needs Postgres at 127.0.0.1:55432 with the API schema applied by the API itself, a built binary and the API's Python deps):

    cargo build --release --manifest-path concierge-stack/server-rs/Cargo.toml
    PYTHONPATH=QA/verification/shims:api python QA/verification/rust_server_parity.py

Starts two loopback servers, sends nothing anywhere, and removes the rows it creates. Compares status, JSON body, content type and the security headers.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "concierge-stack/server-rs/target/release/concierge-server"
PORT = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
DB = f"postgresql://postgres:test@127.0.0.1:{PORT}/postgres"
PY, RS = 8098, 8097
ENV = {"DATABASE_URL": DB, "ADMIN_TOKEN": "parity-admin", "PUBLIC_BASE_URL": "http://localhost:8000", "VOICE_RECORDING_ENABLED": "true", "OUTBOX_ENABLED": "false"}
n = 0
KEEP = ("content-type", "cache-control", "x-content-type-options", "referrer-policy", "access-control-allow-origin")


def psql(sql):
    out = subprocess.run(["psql", DB, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def get(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, body, hdrs = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, body, hdrs = e.code, e.read(), e.headers
    try:
        parsed = json.loads(body) if body else None
    except ValueError:
        parsed = body.decode()
    return status, parsed, {k: hdrs[k] for k in KEEP if hdrs.get(k) is not None}


def wait(port):
    for _ in range(150):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    raise SystemExit(f"server on {port} never became healthy")


def same(label, path, headers=None, normalise=None):
    """The two servers must agree on status, body, content type and security headers."""
    global n
    a, b = get(PY, path, headers), get(RS, path, headers)
    if normalise:
        a, b = normalise(a), normalise(b)
    assert a[0] == b[0], f"{label}: status python={a[0]} rust={b[0]} body={a[1]!r} / {b[1]!r}"
    assert a[1] == b[1], f"{label}: body differs\npython={json.dumps(a[1], indent=1)[:1500]}\nrust  ={json.dumps(b[1], indent=1)[:1500]}"
    for k in ("content-type", "cache-control", "x-content-type-options", "referrer-policy"):
        assert a[2].get(k) == b[2].get(k), f"{label}: header {k} python={a[2].get(k)} rust={b[2].get(k)}"
    n += 1
    print("PASS", label, a[0])
    return a


def main():
    procs = []
    try:
        # the Python API creates/updates the schema on start-up, exactly as in production
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PY)], cwd=ROOT / "api", env={**os.environ, **ENV},
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(PY)
        procs.append(subprocess.Popen([str(BIN)], env={**os.environ, **ENV, "BIND": f"127.0.0.1:{RS}"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(RS)

        psql("DELETE FROM tenants WHERE slug LIKE 'parity-%'")
        rows = [
            ("parity-open", "pk_parity_open", "Open Co", "{}", "true", "", "Friendly."),
            ("parity-closed", "pk_parity_closed", "Closed Co", '{"https://shop.example"}', "false", "Hello from Closed Co!", ""),
            ("parity-trailing", "pk_parity_trailing", "Ünï & Co", '{"https://a.example/","HTTP://B.EXAMPLE"}', "true", "", "p"),
            ("parity-nocal", "pk_parity_nocal", "No Calendar", "{}", "false", "", ""),
        ]
        for slug, key, name, origins, voice, greeting, persona in rows:
            psql(f"INSERT INTO tenants(slug,name,public_key,report_token,allowed_origins,voice_enabled,greeting,persona,site_url) VALUES('{slug}','{name}','{key}','rt_{slug}','{origins}',{voice},'{greeting}','{persona}','https://{slug}.example')")
        psql("UPDATE tenants SET calendar_token='ct_parity_open', scoring='{\"warm_at\": 20}'::jsonb, business_hours='{\"mon\": [[\"09:00\", \"17:00\"]]}'::jsonb WHERE slug='parity-open'")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) SELECT id,'call_recording',true,gen_random_uuid() FROM tenants WHERE slug IN ('parity-open')")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) SELECT id,'call_recording',false,gen_random_uuid() FROM tenants WHERE slug IN ('parity-trailing')")

        psql("INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:p'||g,'t','c',array_fill(0.1::real, ARRAY[384])::vector FROM tenants, generate_series(1,3) g WHERE slug='parity-open'")

        same("healthz", "/healthz")
        for key in ("pk_parity_open", "pk_parity_closed", "pk_parity_trailing", "pk_parity_nocal", "unknown", ""):
            same(f"widget-config {key!r}", f"/api/v1/widget-config?key={key}")
        same("widget-config missing key", "/api/v1/widget-config")
        for origin in ("https://shop.example", "https://SHOP.example/", "https://evil.example", "http://localhost:8000", ""):
            same(f"widget-config closed origin {origin!r}", "/api/v1/widget-config?key=pk_parity_closed", {"Origin": origin})
        for origin in ("https://a.example", "http://b.example", "https://c.example"):
            same(f"widget-config trailing origin {origin!r}", "/api/v1/widget-config?key=pk_parity_trailing", {"Origin": origin})
        same("cors header", "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        a = get(PY, "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        b = get(RS, "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        assert a[2].get("access-control-allow-origin") == b[2].get("access-control-allow-origin") == "*", (a[2], b[2])

        def only_ours(res):
            status, body, hdrs = res
            if isinstance(body, list):
                body = [t for t in body if str(t.get("slug", "")).startswith("parity-")]
            return status, body, hdrs

        same("admin list without token", "/admin/tenants")
        same("admin list wrong token", "/admin/tenants", {"X-Admin-Token": "nope"})
        same("admin list", "/admin/tenants", {"X-Admin-Token": "parity-admin"}, normalise=lambda r: _drop_times(only_ours(r)))
        for slug in ("parity-open", "parity-closed", "parity-nocal", "missing"):
            same(f"admin get {slug}", f"/admin/tenants/{slug}", {"X-Admin-Token": "parity-admin"}, normalise=lambda r: _drop_times(r))
        same("admin get without token", "/admin/tenants/parity-open")
        print(f"{n} comparisons passed")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        psql("DELETE FROM tenants WHERE slug LIKE 'parity-%'")


def _drop_times(res):
    """created_at differs only by insertion time of the shared rows: it is the same row for both servers, so keep it. Tokens minted on first read are random."""
    status, body, hdrs = res
    if isinstance(body, dict) and body.get("slug") == "parity-nocal":
        body = {k: ("<minted>" if k in ("calendar_token", "calendar_url") else v) for k, v in body.items()}
        body["calendar_url"] = "<minted>" if body.get("calendar_url") else body.get("calendar_url")
    return status, body, hdrs


if __name__ == "__main__":
    main()
