"""Smoke probe, 5-minute health check, drift guard and gateway reload for the public tool endpoints.

Written 2026-11-24 after /api/robots died silently. Each guard here has a test that makes it FAIL on a broken
input, then PASS on a good one, so none of them can quietly become a check that always says yes.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
VPS = ROOT / "scripts" / "vps"
sys.path.insert(0, str(VPS))
import tool_endpoints  # noqa: E402

_spec = importlib.util.spec_from_file_location("concierge_healthcheck_tools", VPS / "healthcheck.py")
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

API = {"x-trendi-served-by": "api"}


def fake(table):
    """fetch(url, method, body, timeout) -> (status, headers, body) from {(method, path): response}."""
    calls = []

    def fetch(url, method, body, timeout):
        calls.append((method, url, timeout))
        path = url.split("trendibizz.com", 1)[-1].split("8000", 1)[-1]
        item = table.get((method, path), (404, {"content-type": "application/json"}, b'{"detail":"Not Found"}'))
        return item(url) if callable(item) else item
    fetch.calls = calls
    return fetch


def good_table():
    site = lambda ep: (200, {"content-type": "application/json", **API}, json.dumps({"ok": True, "endpoint": ep}).encode())
    return {
        ("GET", "/api/robots?url=trendibizz.com"): (200, {"content-type": "text/plain; charset=utf-8", "x-trendi-source": "https://trendibizz.com/robots.txt", **API}, b"User-agent: *\nAllow: /\n"),
        ("GET", "/api/site-check"): site("/api/site-check"),
        ("GET", "/api/security-check"): site("/api/security-check"),
        ("POST", "/api/site-check"): (200, {"content-type": "application/json", **API}, json.dumps(
            {"mode": "server", "robots": {}, "sitemap": {}, "onPage": {}, "buckets": {}, "psi": {}, "links": {}}).encode()),
        ("POST", "/api/security-check"): (200, {"content-type": "application/json", **API}, json.dumps(
            {"mode": "server", "checks": [], "groups": {}, "counts": {}, "headers": [], "probes": []}).encode()),
    }


def run(table, functional=True, **kw):
    fetch = fake(table)
    return [tool_endpoints.probe(e, "https://trendibizz.com", fetch=fetch, retry_pause=0, **kw)
            for e in tool_endpoints.ENDPOINTS + (tool_endpoints.FUNCTIONAL if functional else [])]


# ---------------------------------------------------------------------------------- smoke probe
def test_every_tool_endpoint_passes_when_served_correctly():
    results = run(good_table())
    assert len(results) == 5 and all(ok for ok, _ in results), results


def test_endpoints_cover_every_tool_the_pages_call():
    called = {p for p in (ROOT / "scripts" / "verify" / "check_page_api_contract.py").read_text().split() if False}
    names = {e["name"] for e in tool_endpoints.ENDPOINTS}
    assert names == {"/api/robots", "/api/site-check", "/api/security-check"}
    spec = importlib.util.spec_from_file_location("c", ROOT / "scripts" / "verify" / "check_page_api_contract.py")
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    tools = {p for p in contract.page_calls(ROOT) if p != "/api/enquiry"}
    assert tools == names, "a page calls a tool endpoint that tool_endpoints.py does not smoke-test (or the reverse)"
    assert called == set()


@pytest.mark.parametrize("name,breaker,needle", [
    ("missing route (404)", lambda t, k: t.pop(k), "returned HTTP 404, want 200"),
    ("server error", lambda t, k: t.update({k: (502, {"content-type": "text/plain"}, b"bad gateway")}), "returned HTTP 502"),
    ("wrong content type", lambda t, k: t.update({k: (200, {"content-type": "text/html", **API}, b"<html>")}), "Content-Type 'text/html'"),
    ("served by something else", lambda t, k: t.update({k: (200, {"content-type": t[k][1]["content-type"]}, t[k][2])}), "not served by the git-tracked API"),
])
@pytest.mark.parametrize("key", [("GET", "/api/robots?url=trendibizz.com"), ("GET", "/api/site-check"), ("GET", "/api/security-check"),
                                 ("POST", "/api/site-check"), ("POST", "/api/security-check")])
def test_each_endpoint_fails_the_smoke_when_broken(key, name, breaker, needle):
    table = good_table()
    breaker(table, key)
    results = run(table)
    failed = [detail for ok, detail in results if not ok]
    assert len(failed) == 1, (name, results)
    assert needle in failed[0] and key[1].split("?")[0] in failed[0], failed[0]


def test_a_json_body_that_is_wrong_fails():
    table = good_table()
    table[("GET", "/api/site-check")] = (200, {"content-type": "application/json", **API}, b'{"ok": false}')
    assert any("JSON 'ok'" in d for ok, d in run(table) if not ok)
    table = good_table()
    table[("POST", "/api/security-check")] = (200, {"content-type": "application/json", **API}, b'{"mode": "server"}')
    assert any("missing checks" in d for ok, d in run(table) if not ok)


def test_robots_body_must_look_like_a_robots_file():
    table = good_table()
    table[("GET", "/api/robots?url=trendibizz.com")] = (200, {"content-type": "text/plain", "x-trendi-source": "x", **API}, b"<html>oops</html>")
    assert any("body does not look right" in d for ok, d in run(table) if not ok)


def test_a_rate_limited_engine_probe_counts_as_routed_not_failed():
    table = good_table()
    table[("POST", "/api/site-check")] = (429, {"content-type": "application/json", **API}, b'{"error":"rate_limited"}')
    results = run(table)
    assert all(ok for ok, _ in results) and any("HTTP 429 rate limit" in d for _, d in results)
    table[("POST", "/api/site-check")] = (429, {"content-type": "text/html"}, b"cloudflare")
    assert any(not ok for ok, _ in run(table))


def test_no_answer_is_retried_once_then_fails_with_the_reason():
    attempts = []

    def fetch(url, method, body, timeout):
        attempts.append(url)
        return 0, {}, b"TimeoutError: timed out"
    ok, detail = tool_endpoints.probe(tool_endpoints.ENDPOINTS[1], "https://trendibizz.com", fetch=fetch, retry_pause=0)
    assert not ok and len(attempts) == 2
    assert "/api/site-check" in detail and "TimeoutError" in detail


def test_timeout_matches_the_inbound_fix():
    assert tool_endpoints.TIMEOUT == healthcheck.INBOUND_READINESS_TIMEOUT == 30.0
    assert tool_endpoints.RETRY_PAUSE == healthcheck.INBOUND_READINESS_RETRY_PAUSE == 5.0


def test_the_cli_exit_code_is_the_smoke_result(monkeypatch, capsys):
    monkeypatch.setattr(tool_endpoints, "call", fake(good_table()))
    monkeypatch.setattr(tool_endpoints, "RETRY_PAUSE", 0)
    assert tool_endpoints.main(["--base", "https://trendibizz.com", "--functional"]) == 0
    bad = good_table()
    bad.pop(("GET", "/api/robots?url=trendibizz.com"))
    monkeypatch.setattr(tool_endpoints, "call", fake(bad))
    assert tool_endpoints.main(["--base", "https://trendibizz.com"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_only_the_safe_target_is_ever_used():
    text = json.dumps(tool_endpoints.ENDPOINTS + tool_endpoints.FUNCTIONAL)
    assert "trendibizz.com" in text and "example" not in text


# ---------------------------------------------------------------------------------- the 5-minute health check
def patch_probe(monkeypatch, table):
    fetch = fake(table)
    real = tool_endpoints.probe
    monkeypatch.setattr(tool_endpoints, "probe", lambda e, base=tool_endpoints.BASE, **kw: real(e, base, fetch=fetch, **{**kw, "retry_pause": 0}))
    return fetch


def at(minute):
    return datetime(2026, 11, 24, 5, minute, tzinfo=timezone.utc)


def test_healthcheck_is_ok_when_all_tools_answer(monkeypatch):
    fetch = patch_probe(monkeypatch, good_table())
    results = healthcheck.check_tool_endpoints(at(15))
    assert [r["check"] for r in results] == ["tool:/api/robots", "tool:/api/site-check", "tool:/api/security-check"]
    assert all(r["status"] == "ok" for r in results)
    assert all(c[0] == "GET" for c in fetch.calls), "off the hour only the cheap GETs run"
    assert {c[2] for c in fetch.calls} == {30.0}, "30 s timeout like the inbound fix"


def test_healthcheck_runs_the_real_engines_once_an_hour_straight_at_the_api(monkeypatch):
    fetch = patch_probe(monkeypatch, good_table())
    results = healthcheck.check_tool_endpoints(at(0))
    assert len(results) == 5 and all(r["status"] == "ok" for r in results)
    posts = [c for c in fetch.calls if c[0] == "POST"]
    assert len(posts) == 2 and all(c[1].startswith("http://127.0.0.1:8000/") for c in posts), "never a visitor's allowance"


@pytest.mark.parametrize("key,check", [(("GET", "/api/robots?url=trendibizz.com"), "tool:/api/robots"),
                                       (("GET", "/api/site-check"), "tool:/api/site-check"),
                                       (("GET", "/api/security-check"), "tool:/api/security-check")])
def test_a_dead_tool_endpoint_fails_the_check_and_names_endpoint_and_error(monkeypatch, key, check):
    table = good_table()
    table.pop(key)
    patch_probe(monkeypatch, table)
    results = healthcheck.check_tool_endpoints(at(15))
    bad = [r for r in results if r["status"] == "fail"]
    assert [r["check"] for r in bad] == [check]
    assert key[1].split("?")[0] in bad[0]["detail"] and "HTTP 404" in bad[0]["detail"]
    assert healthcheck.mailable({r["check"]: r for r in bad}), "a failing tool check must reach alert.sh"


def test_healthcheck_runs_the_tool_checks_in_main():
    src = (VPS / "healthcheck.py").read_text()
    assert "check_tool_endpoints" in src.split("def main")[1]


# ---------------------------------------------------------------------------------- verify-deploy: smoke + drift
def test_verify_deploy_runs_the_smoke_and_the_drift_guard_and_fails_on_either():
    sh = (VPS / "verify-deploy.sh").read_text()
    main = sh[sh.index('echo "verify-deploy against'):]
    assert main.index("api_drift_guard") < main.index("tool_smoke") < main.index('if [ "$drift" -eq 0 ]')
    assert "tool_endpoints.py" in sh and "--functional" in sh
    assert "drift=1" in sh[sh.index("tool_smoke() {"):sh.index('echo "verify-deploy against')]
    assert 'exit "$drift"' in sh
    assert "-name '*.mjs'" in sh, "website.mjs is host tooling and must be compared too"


def test_drift_guard_asks_the_running_website_container_and_leaves_the_worker_file_alone():
    sh = (VPS / "verify-deploy.sh").read_text()
    guard = sh[sh.index("api_drift_guard() {"):sh.index("tool_smoke() {")]
    assert "podman exec trendi-website-1" in guard and '!= "404"' in guard
    assert "deploy_known_good/_worker.js" in guard and "grep -ao" in guard, "read-only look at the worker file"
    assert " rm " not in guard and "mv " not in guard and "> '$RELEASE" not in guard
    assert "check_page_api_contract.py" in guard and "--paths" in guard
    # regression: an ssh inside `while read` eats the loop's input, so only the first path was ever probed and the
    # guard printed "clean" while the worker still answered (found 2026-11-24 on the first live run)
    assert guard.count('"${SSH[@]}" -n ') == 2, "every ssh in the guard must be ssh -n"
    assert 'probed" -ne "$want"' in guard, "the guard must fail if it probed fewer paths than it listed"


def test_website_container_answers_api_paths_itself_with_404_never_the_worker():
    mjs = (VPS / "website.mjs").read_text()
    guard = mjs.index("apiPath.startsWith('/api/')")
    assert guard < mjs.index("worker.fetch(request,"), "the /api guard must run before the worker is consulted"
    assert "writeHead(404" in mjs[guard:guard + 400]
    assert "const response=await worker.fetch" in mjs, "the worker still serves the static site; it is not removed"


# ---------------------------------------------------------------------------------- gateway reload
def test_sync_tooling_reloads_the_gateway_before_it_verifies():
    sh = (VPS / "sync-tooling.sh").read_text()
    assert sh.index('scripts/vps/reload-gateway.sh"') < sh.index("--- verifying parity")
    assert sh.index("rsync -a --exclude") < sh.index("reload-gateway.sh")


def test_reload_gateway_validates_first_aborts_on_invalid_and_reloads_gracefully():
    sh = (VPS / "reload-gateway.sh").read_text()
    v, r, rs = sh.index("caddy validate --config"), sh.index("caddy reload --config"), sh.index('podman restart \\"')
    assert v < r < rs
    assert "ABORT" in sh and "exit 1" in sh[v:r]
    assert "--adapter caddyfile" in sh
    assert "GATEWAY_VALIDATE_ONLY" in sh and "GATEWAY_CADDYFILE_LOCAL" in sh
    restart = sh[sh.index("else"):]
    assert "no admin API" in restart, "restart is only the one-time bootstrap fallback"


def test_caddyfile_enables_a_loopback_only_admin_api_for_reload():
    caddy = (VPS / "Caddyfile").read_text()
    head = caddy[:caddy.index(":8080 {")]
    assert "admin localhost:2019" in head and "admin off" not in head
    compose = (VPS / "compose.yml").read_text()
    gateway = compose[compose.index("\n  gateway:"):compose.index("Twenty CRM")]
    assert "2019" not in gateway, "the admin port must never be published"


def test_scripts_are_valid_shell():
    for name in ("reload-gateway.sh", "sync-tooling.sh", "verify-deploy.sh", "restart-website.sh", "../seo-gate.sh"):
        done = subprocess.run(["bash", "-n", str(VPS / name)], capture_output=True, text=True)
        assert done.returncode == 0, (name, done.stderr)
