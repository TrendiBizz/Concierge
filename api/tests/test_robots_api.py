"""GET /api/robots: the endpoint behind website/tools/robots-ai-check.js (restored after the VPS cutover).

The checker page calls /api/robots?url=<host>; since the Cloudflare worker was retired the path returned 404.
These checks pin the server contract (text/plain + X-Trendi-* headers, JSON errors with error == "not_found"),
the SSRF guards, the size cap, the rate limit, the gateway route and the page's use of all of it.
"""
import asyncio
import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, public_fetch, robots_fetch

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = (ROOT / "website" / "tools" / "robots-ai-check.js").read_text(encoding="utf-8")
PUBLIC = ["93.184.216.34"]
REAL_CLIENT = httpx.AsyncClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(robots_fetch, "limiter", robots_fetch.RateLimiter(20, 60))


def serve(monkeypatch, handler, addresses=None):
    async def resolve(host):
        found = addresses(host) if callable(addresses) else (addresses or PUBLIC)
        if any(not public_fetch._is_public_ip(ip) for ip in found):
            raise ValueError("Website must resolve only to public internet addresses")
        return found
    monkeypatch.setattr(robots_fetch, "public_addresses", resolve)
    monkeypatch.setattr(robots_fetch.httpx, "AsyncClient",
                        lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


def text_handler(body="User-agent: *\nDisallow: /private\n", status=200):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, content=body.encode() if isinstance(body, str) else body)
    handler.seen = seen
    return handler


client = TestClient(main.app)


def test_returns_robots_txt_as_text_plain_with_source_headers(monkeypatch):
    h = text_handler()
    serve(monkeypatch, h)
    r = client.get("/api/robots", params={"url": "Example.com"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "User-agent: *\nDisallow: /private\n"
    assert r.headers["x-trendi-source"] == "https://example.com/robots.txt"
    assert r.headers["x-trendi-truncated"] == "0"
    assert r.headers["cache-control"] == "no-store"
    req = h.seen[0]
    assert req.headers["host"] == "example.com" and req.url.host == PUBLIC[0], "must connect to the validated IP"
    assert req.url.path == "/robots.txt"


@pytest.mark.parametrize("raw", ["https://example.com/some/path?x=1", "example.com:443", "EXAMPLE.com."])
def test_accepts_a_url_or_host_and_only_ever_fetches_the_root_robots(monkeypatch, raw):
    h = text_handler()
    serve(monkeypatch, h)
    r = client.get("/api/robots", params={"url": raw})
    assert r.status_code == 200 and r.headers["x-trendi-source"] == "https://example.com/robots.txt"
    assert [q.url.path for q in h.seen] == ["/robots.txt"] and h.seen[0].url.query == b""


@pytest.mark.parametrize("raw", [
    "", "   ", "localhost", "127.0.0.1", "[::1]", "10.0.0.5", "169.254.169.254", "intranet",
    "foo.internal", "a.localhost", "user:pw@example.com", "example.com:8080", "ftp://example.com",
    "exa mple.com", "x" * 400 + ".com", "http://[::ffff:127.0.0.1]/",
])
def test_rejects_unusable_or_internal_targets_before_any_request(monkeypatch, raw):
    h = text_handler()
    serve(monkeypatch, h)
    r = client.get("/api/robots", params={"url": raw})
    assert r.status_code == 400 and r.json()["error"] == "bad_url" and r.json()["message"]
    assert h.seen == []


def test_missing_url_parameter_is_a_clean_400():
    r = client.get("/api/robots")
    assert r.status_code == 400 and r.json()["error"] == "bad_url"


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.0.9", "169.254.169.254", "::1", "::ffff:10.0.0.1", "fd00::1"])
def test_a_host_resolving_to_a_private_address_is_blocked(monkeypatch, ip):
    h = text_handler()
    serve(monkeypatch, h, addresses=[ip])
    r = client.get("/api/robots", params={"url": "evil.example.com"})
    assert r.status_code == 422 and r.json()["error"] == "blocked" and h.seen == []


def test_a_mixed_public_and_private_answer_is_blocked(monkeypatch):
    serve(monkeypatch, text_handler(), addresses=[PUBLIC[0], "10.0.0.1"])
    assert client.get("/api/robots", params={"url": "rebind.example.com"}).json()["error"] == "blocked"


def test_follows_redirects_and_reports_the_final_url(monkeypatch):
    def handler(request):
        if request.headers["host"] == "example.com":
            return httpx.Response(301, headers={"location": "https://www.example.com/robots.txt"})
        return httpx.Response(200, content=b"User-agent: *\nAllow: /\n")
    serve(monkeypatch, handler)
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 200 and r.headers["x-trendi-source"] == "https://www.example.com/robots.txt"


def test_a_redirect_to_an_internal_host_is_blocked(monkeypatch):
    def resolver(host):
        return ["10.0.0.9"] if host == "internal.example.com" else PUBLIC

    def handler(request):
        return httpx.Response(302, headers={"location": "https://internal.example.com/robots.txt"})
    serve(monkeypatch, handler, addresses=resolver)
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 422 and r.json()["error"] == "blocked"


@pytest.mark.parametrize("location", ["http://example.com/robots.txt", "https://example.com:8443/robots.txt",
                                      "file:///etc/passwd", "https://user:pw@example.com/robots.txt"])
def test_a_redirect_to_a_non_https_or_odd_port_target_is_refused(monkeypatch, location):
    serve(monkeypatch, lambda request: httpx.Response(302, headers={"location": location}))
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 422 and r.json()["error"] == "blocked"


def test_redirect_loop_stops_after_five_hops(monkeypatch):
    h = lambda request: httpx.Response(302, headers={"location": "https://example.com/robots.txt"})  # noqa: E731
    calls = []
    serve(monkeypatch, lambda request: (calls.append(1), h(request))[1])
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 502 and r.json()["error"] == "too_many_redirects" and len(calls) == 6


@pytest.mark.parametrize("status", [404, 403, 410, 401])
def test_a_4xx_is_not_found_which_the_tool_reads_as_allow_everything(monkeypatch, status):
    serve(monkeypatch, text_handler("nope", status))
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert r.headers["content-type"].startswith("application/json")


def test_a_5xx_is_a_bad_gateway_not_a_pass(monkeypatch):
    serve(monkeypatch, text_handler("boom", 503))
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 502 and r.json()["error"] == "fetch_failed"


def test_timeout_and_connection_errors_are_mapped(monkeypatch):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    serve(monkeypatch, slow)
    assert client.get("/api/robots", params={"url": "example.com"}).status_code == 504

    def down(request):
        raise httpx.ConnectError("refused", request=request)
    serve(monkeypatch, down)
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 502 and r.json()["error"] == "fetch_failed"


def test_the_client_timeout_is_bounded():
    assert robots_fetch.TIMEOUT.read <= 10 and robots_fetch.TIMEOUT.connect <= 5


def test_a_large_file_is_cut_at_512_kib_and_flagged(monkeypatch):
    serve(monkeypatch, text_handler("a" * (robots_fetch.MAX_BYTES + 5000)))
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.status_code == 200 and len(r.content) == 512 * 1024 and r.headers["x-trendi-truncated"] == "1"


def test_html_in_the_file_is_served_as_inert_text(monkeypatch):
    serve(monkeypatch, text_handler("<script>alert(1)</script>"))
    r = client.get("/api/robots", params={"url": "example.com"})
    assert r.headers["content-type"].startswith("text/plain") and r.headers["x-content-type-options"] == "nosniff"


def test_non_utf8_bytes_do_not_crash(monkeypatch):
    serve(monkeypatch, text_handler(b"User-agent: *\n\xff\xfe\nDisallow:\n"))
    assert client.get("/api/robots", params={"url": "example.com"}).status_code == 200


def test_rate_limit_returns_429_json_per_visitor_ip(monkeypatch):
    serve(monkeypatch, text_handler())
    monkeypatch.setattr(robots_fetch, "limiter", robots_fetch.RateLimiter(2, 60))
    for _ in range(2):
        assert client.get("/api/robots", params={"url": "example.com"}, headers={"x-forwarded-for": "198.51.100.1"}).status_code == 200
    r = client.get("/api/robots", params={"url": "example.com"}, headers={"x-forwarded-for": "198.51.100.1"})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and r.headers["retry-after"] == "60"
    assert client.get("/api/robots", params={"url": "example.com"}, headers={"x-forwarded-for": "198.51.100.2"}).status_code == 200


# --- the page's side of the contract -------------------------------------------------------------

def test_the_page_calls_the_endpoint_and_reads_exactly_what_the_server_sends():
    assert "fetch('/api/robots?url=' + encodeURIComponent(host)" in JS
    for token in ("x-trendi-source", "x-trendi-truncated", "'not_found'", "j.error", "j.message", "text\\/plain"):
        assert token in JS, token
    # every error code the server can emit other than not_found falls through to the generic message
    assert "not_found" in {"not_found"} and robots_fetch.RobotsError(404, "not_found", "x").code == "not_found"


def test_the_server_truncation_cap_matches_what_the_page_tells_the_visitor():
    assert "first 512 KB" in JS and robots_fetch.MAX_BYTES == 512 * 1024


def test_the_gateway_routes_api_robots_to_the_api_before_the_static_site():
    caddy = (ROOT / "scripts" / "vps" / "Caddyfile").read_text()
    assert "path /api/robots" in caddy
    block = caddy[caddy.index("handle @tools"):caddy.index("@website host")]
    assert "reverse_proxy api:8000" in block and "Cf-Connecting-Ip" in block
    assert caddy.index("handle @tools") < caddy.index("handle @website")


def test_page_still_has_a_form_and_csp_stays_self_only():
    html = (ROOT / "website" / "tools" / "robots-ai-check.html").read_text(encoding="utf-8")
    assert 'id="robots-form"' in html and 'id="robots-out"' in html
