#!/usr/bin/env python3
"""The public website tool endpoints, and the one probe used to prove they are alive.

Why this exists (2026-11-24): /api/robots silently returned 404 for days after the VPS cutover, because the
only thing serving it was a file that no longer ran. Nothing watched the tool endpoints. This module is the
single list of them, shared by:
  * scripts/vps/verify-deploy.sh   post-deploy smoke:  python3 tool_endpoints.py --base https://trendibizz.com --functional
  * scripts/vps/healthcheck.py     the 5-minute cron (check_tool_endpoints)
  * api/tests/test_tool_endpoints.py

Adding a tool endpoint to the website means adding it to ENDPOINTS here; the page-contract test fails otherwise.

A probe passes only when the status, the Content-Type and the body shape all match AND the response carries
`X-Trendi-Served-By: api`. That header is what proves the route is served by the FastAPI app from git, not by
the legacy worker file on the box (which answers the same GET with the same JSON).

Safe target: only trendibizz.com is ever checked. The site-check and security-check POST probes are limited to
5 per hour per IP by the API, so a 429 {"error": "rate_limited"} counts as "routed and alive" (noted, not failed).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "https://trendibizz.com"
SAFE_SITE = "trendibizz.com"
UA = "trendi-healthcheck/1.0"
TIMEOUT = 30.0          # same as the inbound-readiness fix: a live fetch can take 8-12 s, so 10 s was too tight
RETRY_PAUSE = 5.0       # one retry when there was no HTTP answer at all (timeout, refused, reset)
SERVED_BY = ("x-trendi-served-by", "api")

# Cheap probes (safe to run every five minutes). `json` is a subset the body must contain; `contains` is a
# case-insensitive substring of a text body; `header` must be present.
ENDPOINTS = [
    {"name": "/api/robots", "method": "GET", "path": f"/api/robots?url={SAFE_SITE}", "status": 200,
     "content_type": "text/plain", "contains": "user-agent", "header": "x-trendi-source"},
    {"name": "/api/site-check", "method": "GET", "path": "/api/site-check", "status": 200,
     "content_type": "application/json", "json": {"ok": True, "endpoint": "/api/site-check"}},
    {"name": "/api/security-check", "method": "GET", "path": "/api/security-check", "status": 200,
     "content_type": "application/json", "json": {"ok": True, "endpoint": "/api/security-check"}},
]

# Real checks of the engines themselves (one outbound fetch run each; rate limited, so used sparingly).
FUNCTIONAL = [
    {"name": "/api/site-check (POST)", "method": "POST", "path": "/api/site-check", "body": {"url": f"https://{SAFE_SITE}/"},
     "status": 200, "content_type": "application/json", "accept_429": True,
     "json": {"mode": "server"}, "keys": ["robots", "sitemap", "onPage", "buckets", "psi", "links"]},
    {"name": "/api/security-check (POST)", "method": "POST", "path": "/api/security-check", "body": {"url": f"https://{SAFE_SITE}/"},
     "status": 200, "content_type": "application/json", "accept_429": True,
     "json": {"mode": "server"}, "keys": ["checks", "groups", "counts", "headers", "probes"]},
]


def call(url: str, method: str = "GET", body: dict | None = None, timeout: float = TIMEOUT):
    """Return (status, headers{lowercase}, body bytes). status 0 = no HTTP answer (body holds the reason)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, **({"Content-Type": "application/json"} if data is not None else {})}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read(200_000)
    except Exception as exc:  # noqa: BLE001 - any network failure is a failed probe
        return 0, {}, f"{type(exc).__name__}: {exc}".encode()[:200]


def probe(endpoint: dict, base: str = BASE, timeout: float = TIMEOUT, retry_pause: float = RETRY_PAUSE,
          fetch=None) -> tuple[bool, str]:
    """Return (ok, detail). A failure detail names the endpoint, the URL and the error."""
    fetch = fetch or call  # looked up at call time so tests can replace call()
    url = base.rstrip("/") + endpoint["path"]
    label = f"{endpoint['method']} {url}"
    status, headers, body = fetch(url, endpoint["method"], endpoint.get("body"), timeout)
    if status == 0:  # no HTTP answer at all: one retry rules out a single dropped or slow request
        time.sleep(retry_pause)
        status, headers, body = fetch(url, endpoint["method"], endpoint.get("body"), timeout)
    if status == 0:
        return False, f"{endpoint['name']}: {label} gave no answer ({body.decode(errors='replace')})"
    content_type = headers.get("content-type", "")
    if endpoint.get("accept_429") and status == 429:
        if "application/json" in content_type and b"rate_limited" in body:
            return True, f"{endpoint['name']}: routed and answering (HTTP 429 rate limit; engine not exercised this time)"
        return False, f"{endpoint['name']}: {label} returned HTTP 429 that is not the API's rate_limited JSON"
    if status != endpoint["status"]:
        return False, f"{endpoint['name']}: {label} returned HTTP {status}, want {endpoint['status']}"
    if not content_type.lower().startswith(endpoint["content_type"]):
        return False, f"{endpoint['name']}: {label} returned Content-Type '{content_type}', want {endpoint['content_type']}"
    if headers.get(SERVED_BY[0]) != SERVED_BY[1]:
        return False, (f"{endpoint['name']}: {label} is not served by the git-tracked API "
                       f"(no {SERVED_BY[0]}: {SERVED_BY[1]}); something else is answering this route")
    if endpoint.get("header") and endpoint["header"] not in headers:
        return False, f"{endpoint['name']}: {label} is missing the {endpoint['header']} header"
    if "contains" in endpoint and endpoint["contains"] not in body.decode(errors="replace").lower():
        return False, f"{endpoint['name']}: {label} body does not look right (no '{endpoint['contains']}')"
    if "json" in endpoint or "keys" in endpoint:
        try:
            data = json.loads(body.decode())
        except ValueError:
            return False, f"{endpoint['name']}: {label} body is not JSON"
        for key, want in endpoint.get("json", {}).items():
            if data.get(key) != want:
                return False, f"{endpoint['name']}: {label} JSON {key!r} is {data.get(key)!r}, want {want!r}"
        missing = [k for k in endpoint.get("keys", []) if k not in data]
        if missing:
            return False, f"{endpoint['name']}: {label} JSON is missing {', '.join(missing)}"
    return True, f"{endpoint['name']}: HTTP {status} {content_type.split(';')[0]}"


def run_all(base: str = BASE, functional: bool = False, **kwargs) -> list[tuple[bool, str]]:
    return [probe(e, base, **kwargs) for e in ENDPOINTS + (FUNCTIONAL if functional else [])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test every public website tool endpoint.")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--functional", action="store_true", help="also run the site-check/security-check engines")
    args = parser.parse_args(argv)
    failures = 0
    for ok, detail in run_all(args.base, args.functional):
        print(f"  {'PASS' if ok else 'FAIL'}  {detail}")
        failures += 0 if ok else 1
    print("tool smoke: " + ("OK" if not failures else f"FAIL ({failures} endpoint(s))"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
