"""POST /api/site-check and POST /api/security-check: the endpoints behind website/tools/site-check.js and
security-check.js, ported from the untracked deploy_known_good/_worker.js into the FastAPI app (2026-11-24).

These tests pin: the response contract the page JS reads, the worker's limits (5 per hour per IP, 12 s / 800 KB for
site-check, 10 s / 200 KB for security-check), the SSRF guards (public IPs only, IP-pinned, redirects re-validated,
default ports only), error shapes, and that the page JS still calls and reads exactly what the server sends.
"""
import asyncio
import pathlib
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, public_fetch, site_tools

ROOT = pathlib.Path(__file__).resolve().parents[2]
SITE_JS = (ROOT / "website" / "tools" / "site-check.js").read_text(encoding="utf-8")
SEC_JS = (ROOT / "website" / "tools" / "security-check.js").read_text(encoding="utf-8")
PUBLIC = ["93.184.216.34"]
REAL_CLIENT = httpx.AsyncClient

HOME = (b'<html><head><title>Example Plumbing Auckland - Fast Local Plumbers</title>'
        b'<meta name="description" content="Family plumbers in Auckland. Emergency call outs, hot water and drains, fixed prices and fast service.">'
        b'<link rel="canonical" href="https://example.com/">'
        b'<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization"},{"@type":"WebSite"}]}</script>'
        b'</head><body><h1>Plumbers</h1></body></html>')
ROBOTS = b"User-agent: *\nAllow: /\nUser-agent: GPTBot\nDisallow: /\nSitemap: https://example.com/sitemap.xml\n"
SITEMAP = b'<?xml version="1.0"?><urlset><url><loc>https://example.com/</loc></url><url><loc>https://example.com/a</loc></url></urlset>'


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(site_tools, "site_limiter", site_tools.RateLimiter(5, 3600))
    monkeypatch.setattr(site_tools, "security_limiter", site_tools.RateLimiter(5, 3600))
    monkeypatch.delenv("PAGESPEED_API_KEY", raising=False)


def serve(monkeypatch, handler, addresses=None):
    async def resolve(host):
        found = addresses(host) if callable(addresses) else (addresses or PUBLIC)
        if any(not public_fetch._is_public_ip(ip) for ip in found):
            raise ValueError("Website must resolve only to public internet addresses")
        return found
    monkeypatch.setattr(site_tools, "public_addresses", resolve)
    monkeypatch.setattr(site_tools.httpx, "AsyncClient",
                        lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


def site_handler(overrides=None):
    seen = []
    table = {"/": (200, HOME, {"content-type": "text/html", "x-robots-tag": "all"}), "/robots.txt": (200, ROBOTS, {}),
             "/sitemap.xml": (200, SITEMAP, {}), "/llms.txt": (200, b"# llms\n", {})}
    table.update(overrides or {})

    def handler(request):
        seen.append(request)
        status, body, headers = table.get(request.url.path, (404, b"nope", {}))
        return httpx.Response(status, content=body, headers=headers)
    handler.seen = seen
    return handler


SECURE_HEADERS = {"strict-transport-security": "max-age=63072000", "x-content-type-options": "nosniff",
                  "server": "cloudflare", "content-type": "text/html"}


def sec_handler(overrides=None, headers=None):
    table = {"/": (200, HOME, headers or SECURE_HEADERS), "/robots.txt": (200, ROBOTS, {}), "/sitemap.xml": (200, SITEMAP, {})}
    table.update(overrides or {})
    seen = []

    def handler(request):
        seen.append(request)
        status, body, hdrs = table.get(request.url.path, (404, b"nope", {}))
        return httpx.Response(status, content=body, headers=hdrs)
    handler.seen = seen
    return handler


client = TestClient(main.app)


# ----------------------------------------------------------------------------- site-check contract
def test_site_check_returns_the_snapshot_the_page_reads(monkeypatch):
    h = site_handler()
    serve(monkeypatch, h)
    r = client.post("/api/site-check", json={"url": "https://example.com/"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json") and r.headers["cache-control"] == "no-store"
    assert r.headers["x-trendi-served-by"] == "api"
    d = r.json()
    assert d["mode"] == "server" and d["https"] is True and d["status"] == 200 and d["origin"] == "https://example.com"
    assert d["robots"] == {"googlebot": "allowed", "bingbot": "allowed", "oaiSearchBot": "allowed",
                           "perplexityBot": "allowed", "claudeSearchBot": "allowed"}
    assert d["sitemap"]["found"] is True and d["sitemap"]["urlCount"] == 2
    assert d["llmsTxt"]["found"] is True
    assert d["onPage"]["title"].startswith("Example Plumbing") and d["onPage"]["h1Count"] == 1
    assert d["onPage"]["canonical"] == "https://example.com/"
    assert d["schemaTypes"] == ["Organization", "WebSite"] and d["missingCommonSchema"] == ["Service"]
    assert d["buckets"] == {"indexed": "green", "found": "green", "mentioned": "unknown"}
    assert d["xRobotsTag"] == "all" and d["warnings"] == []
    assert d["psi"]["available"] is False and "PAGESPEED_API_KEY" in d["psi"]["note"]
    assert d["links"]["psi"].startswith("https://pagespeed.web.dev/analysis?url=https%3A%2F%2Fexample.com")
    assert "Mentions in AI answers are not checked" in d["honesty"]
    first = h.seen[0]
    assert first.headers["host"] == "example.com" and first.url.host == PUBLIC[0], "must connect to the validated IP"
    assert first.headers["user-agent"].startswith("TrendiSiteCheck/1.0")


def test_site_check_blocked_googlebot_is_red(monkeypatch):
    serve(monkeypatch, site_handler({"/robots.txt": (200, b"User-agent: Googlebot\nDisallow: /\n", {})}))
    d = client.post("/api/site-check", json={"url": "example.com"}).json()
    assert d["robots"]["googlebot"] == "blocked" and d["buckets"]["indexed"] == "red"


def test_site_check_unreachable_page_still_answers_with_a_warning(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("refused")
    serve(monkeypatch, boom)
    r = client.post("/api/site-check", json={"url": "example.com"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == 0 and d["buckets"]["indexed"] == "red"
    assert any(w.startswith("Could not fetch page") for w in d["warnings"])


def test_site_check_keeps_the_path_but_security_check_uses_the_origin(monkeypatch):
    h = site_handler({"/pricing": (200, HOME, {})})
    serve(monkeypatch, h)
    assert client.post("/api/site-check", json={"url": "https://example.com/pricing"}).json()["url"] == "https://example.com/pricing"
    assert site_tools.normalise("https://example.com/pricing?x=1", keep_path=False)["href"] == "https://example.com/"


def test_pagespeed_key_comes_from_the_environment_and_never_leaks(monkeypatch):
    monkeypatch.setenv("PAGESPEED_API_KEY", "SECRET-KEY-123")
    seen = []

    def psi(request):
        seen.append(request)
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": "key SECRET-KEY-123 is bad"}})
    out = asyncio.run(site_tools.run_psi("https://example.com/", "SECRET-KEY-123", REAL_CLIENT(transport=httpx.MockTransport(psi))))
    assert out["available"] is False and "SECRET-KEY-123" not in str(out) and "[REDACTED]" in out["note"]
    assert seen[0].headers["x-goog-api-key"] == "SECRET-KEY-123"


def test_pagespeed_scores_are_read(monkeypatch):
    payload = {"lighthouseResult": {"categories": {"performance": {"score": 0.91}, "seo": {"score": 1}, "accessibility": {"score": 0.8},
                                                   "best-practices": {"score": 0.77}}, "audits": {}},
               "loadingExperience": {"metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2400},
                                                 "INTERACTION_TO_NEXT_PAINT": {"percentile": 120.4},
                                                 "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 5}}}}
    out = asyncio.run(site_tools.run_psi("https://example.com/", "k", REAL_CLIENT(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))))
    assert out == {"available": True, "strategy": "mobile", "performance": 91, "seo": 100, "accessibility": 80, "bestPractices": 77,
                   "lcp": "2.4s", "inp": "120ms", "cls": "0.05"}


# ----------------------------------------------------------------------------- security-check contract
def test_security_check_returns_the_report_the_page_reads(monkeypatch):
    serve(monkeypatch, sec_handler())
    r = client.post("/api/security-check", json={"url": "example.com"})
    assert r.status_code == 200 and r.headers["x-trendi-served-by"] == "api"
    d = r.json()
    assert d["mode"] == "server" and d["https"] is True and d["status"] == 200 and d["origin"] == "https://example.com"
    ids = [c["id"] for c in d["checks"]]
    assert ids[0] == "https" and "header:strict-transport-security" in ids and "path:/.env" in ids and "path:/admin/" in ids
    assert [p["path"] for p in d["probes"]] == ["/robots.txt", "/sitemap.xml", "/.env", "/.git/config", "/wp-admin/", "/admin/"]
    assert d["counts"] == {k: len(d["groups"][k]) for k in ("pass", "review", "info")}
    assert sum(d["counts"].values()) == len(d["checks"])
    hsts = next(c for c in d["headers"] if c["id"] == "strict-transport-security")
    assert hsts["present"] is True and hsts["bucket"] == "pass" and hsts["valueShown"] == "max-age=63072000"
    csp = next(c for c in d["headers"] if c["id"] == "content-security-policy")
    assert csp["present"] is False and csp["bucket"] == "info"
    assert "not Trendi’s penetration testing service" in d["productNote"] and "penetration-testing" in d["honesty"]
    env = next(p for p in d["probes"] if p["path"] == "/.env")
    assert env["status"] == 404 and env["bucket"] == "pass"


def test_security_check_flags_an_exposed_env_file_and_git_config(monkeypatch):
    serve(monkeypatch, sec_handler({"/.env": (200, b"DB_PASSWORD=hunter2\n", {}), "/.git/config": (200, b"[core]\n\trepositoryformatversion = 0\n", {})}))
    d = client.post("/api/security-check", json={"url": "example.com"}).json()
    by = {p["path"]: p for p in d["probes"]}
    assert by["/.env"]["severity"] == "high" and by["/.env"]["bucket"] == "review"
    assert by["/.git/config"]["severity"] == "high" and "[core]" in by["/.git/config"]["result"]
    assert "hunter2" not in str(d), "never echo the leaked file's contents back"
    assert d["counts"]["review"] >= 2


def test_security_check_missing_hsts_on_https_is_a_review_item(monkeypatch):
    serve(monkeypatch, sec_handler(headers={"content-type": "text/html", "set-cookie": "sid=1; Path=/"}))
    d = client.post("/api/security-check", json={"url": "example.com"}).json()
    hsts = next(c for c in d["headers"] if c["id"] == "strict-transport-security")
    assert hsts["severity"] == "medium" and hsts["bucket"] == "review"
    cookie = next(c for c in d["headers"] if c["id"] == "set-cookie")
    assert cookie["bucket"] == "review" and "Secure flag: not seen" in cookie["result"]


def test_security_check_homepage_unreachable_is_a_502(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("refused")
    serve(monkeypatch, boom)
    r = client.post("/api/security-check", json={"url": "example.com"})
    assert r.status_code == 502
    assert r.json()["error"] == "fetch_failed" and r.json()["message"].startswith("Could not fetch homepage")


def test_security_check_a_failed_probe_is_recorded_not_fatal(monkeypatch):
    def handler(request):
        if request.url.path == "/admin/":
            raise httpx.ReadTimeout("slow")
        return sec_handler()(request)
    serve(monkeypatch, handler)
    d = client.post("/api/security-check", json={"url": "example.com"}).json()
    admin = next(p for p in d["probes"] if p["path"] == "/admin/")
    assert admin["status"] == 0 and admin["result"].startswith("Fetch failed") and "/admin/ fetch failed" in d["warnings"]


# ----------------------------------------------------------------------------- errors and limits (both tools)
@pytest.mark.parametrize("route", ["/api/site-check", "/api/security-check"])
def test_bad_json_and_bad_url_shapes(route):
    assert client.post(route, content=b"not json", headers={"content-type": "application/json"}).json() == {
        "error": "bad_json", "message": "POST JSON { url }."}
    assert client.post(route, json=["x"]).status_code == 400
    r = client.post(route, json={"url": ""})
    assert r.status_code == 400 and r.json() == {"error": "bad_url", "message": "Missing url"}


@pytest.mark.parametrize("route", ["/api/site-check", "/api/security-check"])
@pytest.mark.parametrize("target", [
    "http://localhost/", "https://127.0.0.1/", "http://10.0.0.5/", "https://192.168.1.1/x", "http://169.254.169.254/latest/meta-data/",
    "https://[::1]/", "https://foo.internal/", "https://printer.local/", "https://intranet/", "ftp://example.com/", "file:///etc/passwd",
    "https://user:pw@example.com/", "https://example.com:8443/", "http://example.com:22/", "https://100.64.0.1/",
])
def test_internal_and_odd_targets_are_refused_before_any_request(monkeypatch, route, target):
    h = site_handler()
    serve(monkeypatch, h)
    r = client.post(route, json={"url": target})
    assert r.status_code == 400 and r.json()["error"] == "bad_url", target
    assert h.seen == [], "nothing may be fetched for a refused target"


def test_hostnames_that_resolve_to_private_addresses_are_not_fetched(monkeypatch):
    h = site_handler()
    serve(monkeypatch, h, addresses=["10.0.0.9"])
    d = client.post("/api/site-check", json={"url": "rebind.example.com"}).json()
    assert d["status"] == 0 and h.seen == []
    assert client.post("/api/security-check", json={"url": "rebind.example.com"}).status_code == 502


def test_mixed_public_and_private_dns_answers_are_refused(monkeypatch):
    h = site_handler()
    serve(monkeypatch, h, addresses=["93.184.216.34", "127.0.0.1"])
    assert client.post("/api/security-check", json={"url": "rebind.example.com"}).status_code == 502
    assert h.seen == []


def test_redirects_are_followed_but_each_hop_is_revalidated(monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt" or request.url.path == "/":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(404)
    serve(monkeypatch, handler)
    d = client.post("/api/site-check", json={"url": "example.com"}).json()
    assert d["status"] == 0 and any("Could not fetch page" in w for w in d["warnings"])
    assert client.post("/api/security-check", json={"url": "example.com"}).status_code == 502


def test_a_public_redirect_is_followed_to_the_final_url(monkeypatch):
    def handler(request):
        if request.url.path == "/" and request.headers["host"] == "example.com":
            return httpx.Response(301, headers={"location": "https://www.example.com/home"})
        if request.headers["host"] == "www.example.com" and request.url.path == "/home":
            return httpx.Response(200, content=HOME, headers={"content-type": "text/html"})
        return httpx.Response(404)
    serve(monkeypatch, handler)
    d = client.post("/api/site-check", json={"url": "example.com"}).json()
    assert d["url"] == "https://www.example.com/home" and d["status"] == 200


def test_redirect_loops_stop_after_five_hops(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "/again"})
    serve(monkeypatch, handler)
    assert client.post("/api/security-check", json={"url": "example.com"}).status_code == 502
    assert len([c for c in calls if c.url.path in ("/", "/again")]) <= 6 * 7


def test_plain_http_sites_are_checked_on_port_80_and_reported_not_https(monkeypatch):
    h = sec_handler()
    serve(monkeypatch, h)
    d = client.post("/api/security-check", json={"url": "http://example.com"}).json()
    assert d["https"] is False and d["checks"][0]["bucket"] == "review" and d["checks"][0]["result"] == "Final URL was not HTTPS."
    assert h.seen[0].url.scheme == "http" and h.seen[0].url.port in (None, 80)


def test_response_bodies_are_capped(monkeypatch):
    big = b"x" * 3_000_000
    serve(monkeypatch, lambda request: httpx.Response(200, content=big))
    sec = asyncio.run(site_tools.fetch_text("https://example.com/", ua="t", timeout=5, max_bytes=site_tools.SEC_MAX_BYTES))
    site = asyncio.run(site_tools.fetch_text("https://example.com/", ua="t", timeout=5, max_bytes=site_tools.SITE_MAX_BYTES))
    assert len(sec.text) == 200_000 and len(site.text) == 800_000


def test_the_worker_limits_are_kept():
    assert (site_tools.SITE_TIMEOUT, site_tools.SITE_MAX_BYTES) == (12.0, 800_000)
    assert (site_tools.SEC_TIMEOUT, site_tools.SEC_MAX_BYTES) == (10.0, 200_000)
    assert site_tools.PSI_TIMEOUT == 45.0
    assert (site_tools.site_limiter.limit, site_tools.site_limiter.window) == (5, 3600)
    assert (site_tools.security_limiter.limit, site_tools.security_limiter.window) == (5, 3600)


def test_a_slow_site_times_out_instead_of_hanging(monkeypatch):
    async def slow(*a, **k):
        await asyncio.sleep(5)
    monkeypatch.setattr(site_tools, "_hop", slow)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(site_tools.fetch_text("https://example.com/", ua="t", timeout=0.05, max_bytes=10))


@pytest.mark.parametrize("route", ["/api/site-check", "/api/security-check"])
def test_the_sixth_check_in_an_hour_from_one_ip_is_429(monkeypatch, route):
    serve(monkeypatch, sec_handler() if "security" in route else site_handler())
    for _ in range(5):
        assert client.post(route, json={"url": "example.com"}, headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200
    r = client.post(route, json={"url": "example.com"}, headers={"x-forwarded-for": "203.0.113.9"})
    assert r.status_code == 429
    assert r.json() == {"error": "rate_limited", "message": "Limit is 5 checks per hour per IP (MVP). Try again later."}
    assert client.post(route, json={"url": "example.com"}, headers={"x-forwarded-for": "203.0.113.10"}).status_code == 200


def test_the_two_tools_have_separate_allowances(monkeypatch):
    serve(monkeypatch, site_handler())
    for _ in range(5):
        client.post("/api/site-check", json={"url": "example.com"}, headers={"x-forwarded-for": "198.51.100.1"})
    assert client.post("/api/security-check", json={"url": "example.com"}, headers={"x-forwarded-for": "198.51.100.1"}).status_code != 429


@pytest.mark.parametrize("route", ["/api/site-check", "/api/security-check"])
def test_get_is_the_liveness_document_and_options_is_cors(route):
    r = client.get(route)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json()["ok"] is True and r.json()["endpoint"] == route and r.headers["x-trendi-served-by"] == "api"
    o = client.options(route)
    assert o.status_code == 204 and o.headers["access-control-allow-origin"] == "https://trendibizz.com"


# ----------------------------------------------------------------------------- the pages' side of the contract
def test_site_check_page_calls_the_endpoint_and_reads_what_the_server_sends():
    assert 'fetch("/api/site-check"' in SITE_JS and 'method: "POST"' in SITE_JS and "JSON.stringify({ url: target.href })" in SITE_JS
    assert 'res.status === 404' in SITE_JS, "a 404 must still fall back to limited mode"
    for key in ("data.robots", "data.sitemap", "data.onPage", "data.buckets", "data.psi", "data.links", "data.warnings", "data.schemaTypes"):
        assert key in SITE_JS or key.split(".")[1] in SITE_JS, key
    assert "data.message || data.error" in SITE_JS


def test_security_check_page_calls_the_endpoint_and_reads_what_the_server_sends():
    assert 'fetch("/api/security-check"' in SEC_JS and 'method: "POST"' in SEC_JS and "JSON.stringify({ url: target.href })" in SEC_JS
    assert "err.status === 429" in SEC_JS and "data.message || data.error" in SEC_JS
    assert "Limit is 5 checks per hour per IP" in SEC_JS
    for key in ("data.groups", "data.checks", "data.counts", "data.warnings", "data.honesty", "data.productNote", "data.url"):
        assert key in SEC_JS, key


def test_every_key_the_pages_read_is_in_the_real_response(monkeypatch):
    """Derive the keys from the page JS itself, so adding a read to the page without the server fails here."""
    serve(monkeypatch, sec_handler())
    sec = client.post("/api/security-check", json={"url": "example.com"}).json()
    serve(monkeypatch, site_handler())
    site = client.post("/api/site-check", json={"url": "example.com"}).json()
    client_side = {"message", "error"}  # error documents only; mode is set by the page when absent
    sec_read = set(re.findall(r"\bdata\.([A-Za-z]+)", SEC_JS)) - client_side
    site_read = set(re.findall(r"\bdata\.([A-Za-z]+)", SITE_JS)) - client_side
    assert sec_read >= {"groups", "checks", "counts", "warnings", "honesty", "productNote", "url", "mode"}
    assert site_read >= {"robots", "sitemap", "onPage", "buckets", "psi", "links", "warnings", "schemaTypes", "mode"}
    assert sec_read - set(sec) == set(), f"security-check page reads keys the server does not send: {sec_read - set(sec)}"
    assert site_read - set(site) == set(), f"site-check page reads keys the server does not send: {site_read - set(site)}"


def test_the_gateway_sends_both_tools_to_the_api_before_the_static_site():
    caddy = (ROOT / "scripts" / "vps" / "Caddyfile").read_text()
    block = caddy[caddy.index("@tools {"):caddy.index("@website host")]
    for path in ("/api/robots", "/api/site-check", "/api/security-check"):
        assert path in block
    assert "reverse_proxy api:8000" in block and "Cf-Connecting-Ip" in block
    assert caddy.index("handle @tools") < caddy.index("handle @website")


def test_the_api_container_receives_the_pagespeed_key_file():
    compose = (ROOT / "scripts" / "vps" / "compose.yml").read_text()
    api = compose[compose.index("\n  api:"):compose.index("\n  gateway:")]
    assert "/opt/trendi/shared/website.env" in api
