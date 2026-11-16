"""The health check must read a whole JSON body, and must not blame Cloudflare for its own fault.

Measured 2026-11-16: two checks failed at once — `inbound:readiness: unparseable response` and
`cloudflare:routing: 0 enabled rules (expected >=5)`. Both APIs were answering valid JSON. The
helper read only 4096 bytes (`response.read(read_limit)`), so any JSON document bigger than that
arrived truncated: the inbound payload had just crossed it at 4,757 bytes when one tenant was
added, and the email-routing rules response is larger than 4 KB whenever it carries real
descriptions. The routing check swallowed the parse error and reported "0 enabled rules", which
sent the operator to Cloudflare looking for rules that had never been deleted.
"""

import importlib.util
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_reads", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)


class Handler(BaseHTTPRequestHandler):
    payload = b"{}"

    def do_GET(self):  # noqa: N802 - the stdlib names it
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *args):
        pass


def serve(payload: bytes):
    handler = type("H", (Handler,), {"payload": payload})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def test_a_json_body_larger_than_4kb_is_read_whole():
    body = json.dumps({"tenants": [{"slug": f"tenant-{i}", "checks": {"x": "y" * 40}} for i in range(120)]}).encode()
    assert len(body) > 4096, "the fixture must be bigger than the old limit to prove anything"
    server, url = serve(body)
    try:
        status, got, _ = healthcheck.http(url)
    finally:
        server.shutdown()
    assert status == 200
    assert len(got) == len(body), f"read {len(got)} of {len(body)} bytes — the body was truncated"
    assert json.loads(got)["tenants"][-1]["slug"] == "tenant-119"


def test_a_truncated_rules_response_is_not_reported_as_zero_rules(monkeypatch):
    """The old text sent the operator hunting for deleted Cloudflare rules. Say what happened."""
    calls = {"n": 0}

    def fake_http(url, *args, **kwargs):
        calls["n"] += 1
        if "tokens/verify" in url:
            return 200, b'{"result":{"status":"active"}}', 0.01
        if "email/routing/rules" in url:
            return 200, b'{"result":[{"enabled":true},', 0.01   # cut off
        return 200, b"{}", 0.01

    monkeypatch.setattr(healthcheck, "http", fake_http)
    results = healthcheck.check_cloudflare({
        "CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ZONE_ID": "z",
        "CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_WORKER_NAME": "w"})
    routing = [r for r in results if r["check"] == "cloudflare:routing"][0]
    assert routing["status"] == "fail"
    assert "unparseable" in routing["detail"]
    assert "0 enabled rules" not in routing["detail"]


def test_a_new_tenant_is_split_into_onboarding_not_breakage():
    live, test, onboarding = healthcheck.chain_split([
        {"slug": "real", "ok": False},
        {"slug": "fictitious", "ok": False, "is_test": True},
        {"slug": "new", "ok": False, "is_new": True},
        {"slug": "green", "ok": True},
    ])
    assert [t["slug"] for t in live] == ["real"]
    assert [t["slug"] for t in test] == ["fictitious"]
    assert [t["slug"] for t in onboarding] == ["new"]


def test_the_database_check_does_not_reference_inbound_state(monkeypatch):
    """A warning block landed in `check_database` and crashed the whole report with
    `name 'onboarding' is not defined` — a NameError in a function nothing exercised. Call it."""
    monkeypatch.setattr(healthcheck, "run", lambda *args, **kwargs: (0, "1"))
    results = healthcheck.check_database()
    assert [r["check"] for r in results] == ["postgres:query", "postgres:tenants"]
