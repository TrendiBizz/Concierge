"""POST /api/site-check and POST /api/security-check: the public website tools, served from git.

These two endpoints used to live only in /website/deploy_known_good/_worker.js on the box (an untracked file the
website container loaded at start). They are ported here so the routes no longer depend on that file.

Contract (pinned by website/tools/site-check.js, security-check.js and tests/test_site_tools_api.py):
  POST {"url": "<site>"} -> 200 JSON (mode "server")      GET -> 200 {"ok": true, "endpoint": ...} (liveness/smoke)
  400 {"error": "bad_json"|"bad_url", "message"}          429 {"error": "rate_limited", "message"}
  502 {"error": "fetch_failed", ...} (security-check, homepage unreachable)
Limits kept from the worker: 5 checks per hour per IP per tool; site-check requests 12 s each with an 800 KB cap,
security-check probes 10 s each with a 200 KB cap, PageSpeed 45 s. Every hop is public-only and IP-pinned:
only http (port 80) and https (port 443) are fetched, redirects are followed manually (max 5) and re-validated.
"""
import asyncio
import ipaddress
import json
import os
import re
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .public_fetch import _is_public_ip, public_addresses
from .security import RateLimiter

MAX_REDIRECTS = 5
SITE_TIMEOUT, SITE_MAX_BYTES = 12.0, 800_000
SEC_TIMEOUT, SEC_MAX_BYTES = 10.0, 200_000
PSI_TIMEOUT = 45.0
SITE_UA = "TrendiSiteCheck/1.0 (+https://trendibizz.com/tools/site-check.html)"
SEC_UA = "TrendiSecurityCheck/1.0 (+https://trendibizz.com/tools/security-check)"
site_limiter = RateLimiter(5, 3600)      # "Limit is 5 checks per hour per IP"
security_limiter = RateLimiter(5, 3600)
RATE_MESSAGE = "Limit is 5 checks per hour per IP (MVP). Try again later."


class ToolError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


class Fetched:
    def __init__(self, status: int, final_url: str, headers: dict, text: str) -> None:
        self.status, self.final_url, self.headers, self.text = status, final_url, headers, text

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


# ----------------------------------------------------------------------------- input and safe fetching
def normalise(raw, keep_path: bool) -> dict:
    """Return {origin, href, host}. Public http(s) hostnames on the default port only (raise ToolError 400)."""
    text = str(raw or "").strip()
    if not text:
        raise ToolError(400, "bad_url", "Missing url")
    if text.startswith("//"):
        text = "https:" + text
    if not re.match(r"^[a-z][a-z0-9+.-]*:", text, re.I):
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").rstrip(".").lower()
        port = parts.port
    except ValueError:
        raise ToolError(400, "bad_url", "Invalid url") from None
    if parts.scheme not in ("http", "https"):
        raise ToolError(400, "bad_url", "Only http(s) URLs")
    if parts.username or parts.password or port not in (None, 80 if parts.scheme == "http" else 443):
        raise ToolError(400, "bad_url", "Only sites on the default web port can be checked.")
    if _is_internal_name(host):
        raise ToolError(400, "bad_url", "Public hostnames only")
    origin = f"{parts.scheme}://{host}"
    path = parts.path if keep_path and parts.path and parts.path != "/" else "/"
    return {"origin": origin, "href": origin + path, "host": host}


def _is_internal_name(host: str) -> bool:
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        return not _is_public_ip(str(ipaddress.ip_address(host)))
    except ValueError:
        return "." not in host  # a bare label such as "intranet" is never a public site


async def _hop(client: httpx.AsyncClient, url: str, accept: str, ua: str, max_bytes: int):
    parts = urlsplit(url)
    host = (parts.hostname or "").rstrip(".").lower()
    port = parts.port
    if (parts.scheme not in ("http", "https") or parts.username or parts.password
            or port not in (None, 80 if parts.scheme == "http" else 443) or _is_internal_name(host)):
        raise ValueError("Only public sites on the default web port can be checked")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await public_addresses(host)
    if any(not _is_public_ip(ip) for ip in addresses):
        raise ValueError("Website must resolve only to public internet addresses")
    target = httpx.URL(url).copy_with(host=addresses[0])
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
    async with client.stream("GET", target, headers={"Host": host, "User-Agent": ua, "Accept": accept},
                             extensions=extensions, follow_redirects=False) as response:
        body = bytearray()
        if not response.is_redirect:
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    del body[max_bytes:]
                    break
        return response, bytes(body)


async def fetch_text(url: str, *, accept: str = "*/*", ua: str, timeout: float, max_bytes: int,
                     client: httpx.AsyncClient | None = None) -> Fetched:
    """GET with manual, re-validated redirects. Raises httpx errors, ValueError (blocked) or ToolError."""
    owns = client is None
    if owns:
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)), follow_redirects=False)
    try:
        async def run():
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                response, body = await _hop(client, current, accept, ua, max_bytes)
                if response.is_redirect and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    continue
                headers = {k.lower(): v for k, v in response.headers.items()}
                return Fetched(response.status_code, current, headers, body.decode("utf-8", errors="replace"))
            raise ToolError(502, "too_many_redirects", "Too many redirects.")
        return await asyncio.wait_for(run(), timeout)  # the worker aborted each request after `timeout`
    finally:
        if owns:
            await client.aclose()


def error_name(error: Exception) -> str:
    if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "TimeoutError"
    return "error"


# ----------------------------------------------------------------------------- security-check
PROBES = [
    {"path": "/robots.txt", "label": "robots.txt", "kind": "meta", "meaning": "Public file that tells crawlers what they may fetch. We only check whether it responds."},
    {"path": "/sitemap.xml", "label": "sitemap.xml", "kind": "meta", "meaning": "Public sitemap used by search engines. We only check whether it responds at the common path."},
    {"path": "/.env", "label": "/.env", "kind": "sensitive", "meaning": "Environment files often hold API keys and passwords. They must never be public on the web."},
    {"path": "/.git/config", "label": "/.git/config", "kind": "sensitive", "meaning": "Git metadata. If public, attackers can sometimes download source history."},
    {"path": "/wp-admin/", "label": "/wp-admin/", "kind": "admin", "meaning": "Common WordPress admin URL. A login page may be fine; confirm it should be on the public internet."},
    {"path": "/admin/", "label": "/admin/", "kind": "admin", "meaning": "Common admin URL. We only check whether something answers — not whether we can log in."},
]
HEADERS = [
    ("strict-transport-security", "HSTS (Strict-Transport-Security)", "Tells browsers to keep using HTTPS for this site for a set time, which reduces SSL-stripping risk.", True),
    ("content-security-policy", "Content-Security-Policy (CSP)", "Limits which scripts, images, and embeds the page may load. Helps reduce XSS impact when configured well.", False),
    ("x-frame-options", "X-Frame-Options", "Helps stop other sites from embedding yours in a frame (clickjacking). Modern sites may use CSP frame-ancestors instead.", True),
    ("x-content-type-options", "X-Content-Type-Options", "When set to nosniff, browsers will not guess a different content type than the server declared.", True),
    ("referrer-policy", "Referrer-Policy", "Controls how much of the page URL is sent when people click outbound links.", True),
    ("permissions-policy", "Permissions-Policy", "Limits browser features the page (and embeds) can use, such as camera or microphone.", True),
]


def _bucket(severity: str) -> str:
    return "pass" if severity == "ok" else "review" if severity in ("high", "medium") else "info"


def _value(raw, show_all: bool) -> dict:
    if not raw:
        return {"value": None, "valueShown": None, "valueTruncated": False, "valueLength": 0}
    text, n = str(raw), len(str(raw))
    if show_all or n <= 80:
        return {"value": text, "valueShown": text, "valueTruncated": False, "valueLength": n}
    return {"value": text, "valueShown": text[:80] + "…", "valueTruncated": True, "valueLength": n}


def classify_probe(probe: dict, status: int, body: str) -> dict:
    text, kind, path = (body or "")[:4000], probe["kind"], probe["path"]

    def out(severity, bucket, result, next_step):
        return {"severity": severity, "bucket": bucket, "result": result, "nextStep": next_step}

    if path == "/.env" and status == 200 and ("=" in text or re.search(r"^(?:export\s+)?[A-Z0-9_]+=", text, re.M)):
        return out("high", "review", "Public response looks like an environment file (KEY=value style text).",
                   "Block web access to /.env immediately. Rotate any secrets that may have been exposed.")
    if path == "/.git/config" and status == 200 and re.search(r"\[core\]", text, re.I):
        return out("high", "review", "Public response looks like a Git config ([core] section found).",
                   "Block web access to /.git. Assume source may have been readable.")
    if kind == "sensitive":
        if status in (404, 410):
            return out("ok", "pass", f"Not publicly found (HTTP {status}).", "Good for this light check. Keep this path blocked in production.")
        if status in (401, 403):
            return out("ok", "pass", f"Server blocked or required auth (HTTP {status}).", "Fine for this light check. We did not try to bypass auth.")
        if 200 <= status < 400:
            return out("medium", "review", f"Path responded HTTP {status}. Treat as potentially exposed until you confirm the body is harmless.",
                       "Open the URL yourself and confirm it is not leaking secrets. Prefer blocking it at the web server or CDN.")
    if kind == "admin":
        if status in (404, 410):
            return out("ok", "pass", f"No public page at this common admin path (HTTP {status}).", "Nothing to do for this path in this light check.")
        if status in (401, 403):
            return out("ok", "pass", f"Admin path requires auth or is blocked (HTTP {status}).", "Still consider IP allowlists or SSO for admin areas.")
        if 200 <= status < 400:
            return out("medium", "review", f"Something public answered at this admin path (HTTP {status}). Often a login page.",
                       "Confirm the admin area should be public. Prefer strong auth, rate limits, and IP allowlists where practical.")
    if kind == "meta":
        if 200 <= status < 400:
            return out("info", "info", f"File responded HTTP {status}. That is normal for many sites.", "Informational only for security. Use the site snapshot for crawl/SEO detail.")
        if status in (404, 410):
            return out("info", "info", f"Not found at the common path (HTTP {status}).", "Optional for security. May matter for SEO crawl readiness.")
    if status == 0:
        return out("info", "info", "Could not fetch this path (timeout, network error, or remote block).",
                   "Retry later. If it keeps failing, check the host from your own browser.")
    return out("info", "info", f"Path returned HTTP {status}.", "Recorded for awareness only.")


def analyse_headers(headers: dict, https: bool) -> list:
    found = []
    for name, label, meaning, short_safe in HEADERS:
        raw = headers.get(name)
        if raw:
            found.append({"id": name, "label": label, "present": True, "severity": "ok", "bucket": "pass", "meaning": meaning,
                          "result": "Header is present on the homepage response.",
                          "nextStep": "Present is a good hardening signal for this light check. Review the value with your developer if you change hosting.",
                          **_value(raw, short_safe or len(str(raw)) <= 80)})
        else:
            sev = "medium" if name == "strict-transport-security" and https else "info"
            found.append({"id": name, "label": label, "present": False, "severity": sev, "bucket": _bucket(sev), "meaning": meaning,
                          "result": "Not seen on the homepage response.",
                          "nextStep": ("Add HSTS at the CDN or web server once HTTPS is solid (includeSubDomains only if all subdomains are ready)."
                                       if sev == "medium" else "Optional hardening for many small sites. Missing does not mean the site is compromised."),
                          **_value(None, False)})
    if headers.get("server"):
        found.append({"id": "server", "label": "Server", "present": True, "severity": "info", "bucket": "info",
                      "meaning": "Some hosts advertise software or CDN names in the Server header.",
                      "result": "Server header is present.", "nextStep": "Presence only. We do not fingerprint or exploit versions.",
                      **_value(headers["server"], True)})
    cookie = headers.get("set-cookie")
    if cookie:
        secure, httponly = bool(re.search(r";\s*secure\b", cookie, re.I)), bool(re.search(r";\s*httponly\b", cookie, re.I))
        sev = "medium" if https and not secure else "info"
        found.append({"id": "set-cookie", "label": "Set-Cookie flags (homepage)", "present": True, "severity": sev, "bucket": _bucket(sev),
                      "meaning": "Cookies on HTTPS pages should usually include Secure (and often HttpOnly) flags.",
                      "result": f"Homepage set a cookie. Secure flag: {'seen' if secure else 'not seen'}. HttpOnly flag: {'seen' if httponly else 'not seen'}.",
                      "nextStep": ("Ask your developer to set Secure on cookies used over HTTPS. Other cookies on other pages may differ."
                                   if sev == "medium" else "Flags checked only on this homepage response — not a full session audit."),
                      **_value(None, False)})
    return found


def build_checks(https: bool, status: int, header_findings: list, probes: list) -> list:
    meaning = "Visitors should land on https:// so traffic between browser and server is encrypted."
    if not https:
        first = {"id": "https", "title": "HTTPS on homepage", "bucket": "review", "severity": "high", "meaning": meaning,
                 "result": "Final URL was not HTTPS.", "nextStep": "Turn on HTTPS and redirect HTTP → HTTPS at the host or CDN."}
    elif 200 <= status < 400:
        first = {"id": "https", "title": "HTTPS on homepage", "bucket": "pass", "severity": "ok", "meaning": meaning,
                 "result": f"Homepage reached over HTTPS (HTTP {status}).", "nextStep": "Baseline only. HTTPS reachability is not a full security pass."}
    else:
        first = {"id": "https", "title": "HTTPS on homepage", "bucket": "info", "severity": "info", "meaning": meaning,
                 "result": f"Unusual homepage status: HTTP {status}.", "nextStep": "Fix reachability before judging hardening headers."}
    checks = [first]
    for h in header_findings:
        checks.append({"id": "header:" + h["id"], "title": h["label"], "bucket": h["bucket"], "severity": h["severity"], "meaning": h["meaning"],
                       "result": h["result"], "nextStep": h["nextStep"], "value": h["value"], "valueShown": h["valueShown"],
                       "valueTruncated": h["valueTruncated"], "valueLength": h["valueLength"], "present": h["present"]})
    for p in probes:
        checks.append({"id": "path:" + p["path"], "title": p["label"], "bucket": p["bucket"], "severity": p["severity"], "meaning": p["meaning"],
                       "result": f"{p['result']} (HTTP {p['status']})", "nextStep": p["nextStep"], "status": p["status"], "kind": p["kind"]})
    return checks


async def security_check(raw_url, client: httpx.AsyncClient | None = None) -> dict:
    target = normalise(raw_url, keep_path=False)

    async def probe(url, accept):
        return await fetch_text(url, accept=accept, ua=SEC_UA, timeout=SEC_TIMEOUT, max_bytes=SEC_MAX_BYTES, client=client)

    try:
        home = await probe(target["href"], "text/html,*/*")
    except (ToolError, ValueError, httpx.HTTPError, asyncio.TimeoutError) as error:
        raise ToolError(502, "fetch_failed", f"Could not fetch homepage ({error_name(error)}).", url=target["href"]) from None
    https = home.final_url.startswith("https:")
    header_findings = analyse_headers(home.headers, https)
    warnings: list = []

    async def one(p):
        url = target["origin"] + p["path"]
        accept = "text/plain,application/xml,*/*" if p["kind"] == "meta" else "*/*"
        try:
            r = await probe(url, accept)
        except (ToolError, ValueError, httpx.HTTPError, asyncio.TimeoutError) as error:
            warnings.append(p["path"] + " fetch failed")
            return {"path": p["path"], "label": p["label"], "kind": p["kind"], "meaning": p["meaning"], "status": 0, "finalUrl": url,
                    "severity": "info", "bucket": "info", "result": f"Fetch failed ({error_name(error)}).",
                    "nextStep": "Retry later from your own browser if this keeps failing."}
        verdict = classify_probe(p, r.status, r.text)
        return {"path": p["path"], "label": p["label"], "kind": p["kind"], "meaning": p["meaning"], "status": r.status,
                "finalUrl": r.final_url, **verdict}

    probes = list(await asyncio.gather(*(one(p) for p in PROBES)))
    checks = build_checks(https, home.status, header_findings, probes)
    groups = {b: [c for c in checks if c["bucket"] == b] for b in ("pass", "review", "info")}
    return {
        "mode": "server", "url": home.final_url or target["href"], "origin": target["origin"], "https": https, "status": home.status,
        "headers": header_findings, "probes": probes, "checks": checks, "groups": groups,
        "counts": {k: len(v) for k, v in groups.items()}, "warnings": warnings,
        "productNote": "This tool is a light public hygiene check. It is not Trendi’s penetration testing service, not a compliance audit, and not a promise the site is hack-proof.",
        "honesty": "Presence/absence only: homepage HTTPS, security-related headers, and a few common paths. No exploit payloads, no login attempts, no authenticated testing. For a scoped pen-test quote: https://trendibizz.com/penetration-testing",
    }


# ----------------------------------------------------------------------------- site-check
AI_BOTS = [
    ("googlebot", "Googlebot", re.compile(r"googlebot", re.I)),
    ("bingbot", "Bingbot", re.compile(r"bingbot", re.I)),
    ("oaiSearchBot", "OAI-SearchBot", re.compile(r"oai-searchbot", re.I)),
    ("perplexityBot", "PerplexityBot", re.compile(r"perplexitybot", re.I)),
    ("claudeSearchBot", "Claude-SearchBot", re.compile(r"claude-searchbot", re.I)),
]


def parse_robots(text: str):
    groups, sitemaps, current = [], [], None
    for line in text.splitlines():
        line = re.sub(r"#.*", "", line).strip()
        m = re.match(r"^(user-agent|allow|disallow|sitemap)\s*:\s*(.*)$", line, re.I) if line else None
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "user-agent":
            current = {"ua": value, "rules": []}
            groups.append(current)
        elif key == "sitemap":
            sitemaps.append(value)
        elif current is not None:
            current["rules"].append({"type": key, "path": value})
    return groups, sitemaps


def match_group(groups, name, pattern):
    star = matched = None
    for g in groups:
        if g["ua"] == "*":
            star = g
        if pattern.search(g["ua"]):
            matched = g
        if g["ua"].lower() == name.lower():
            matched = g
    return matched or star


def root_allowed(group) -> str:
    if not group:
        return "unknown"
    rules = [r for r in group["rules"] if r["type"] in ("allow", "disallow")]
    blocked = any(r["type"] == "disallow" and r["path"] in ("/", "/*") for r in rules)
    allowed = any(r["type"] == "allow" and r["path"] in ("/", "/*", "") for r in rules)
    all_empty = bool(rules) and all(r["type"] == "disallow" and r["path"] == "" for r in rules)
    if blocked and not allowed:
        return "blocked"
    if all_empty or allowed or not rules:
        return "allowed"
    if any(r["type"] == "disallow" and r["path"] for r in rules):
        return "partial"
    return "allowed"


def analyse_robots(text: str):
    groups, sitemaps = parse_robots(text or "")
    return {key: root_allowed(match_group(groups, name, pat)) for key, name, pat in AI_BOTS}, sitemaps


def _tag(pattern_a, pattern_b, html):
    m = re.search(pattern_a, html, re.I) or re.search(pattern_b, html, re.I)
    return m.group(1).strip() if m else ""


def _collect_types(node, out):
    if isinstance(node, list):
        for item in node:
            _collect_types(item, out)
    elif isinstance(node, dict):
        if node.get("@type"):
            t = node["@type"]
            out.extend(str(x) for x in t) if isinstance(t, list) else out.append(str(t))
        if node.get("@graph"):
            _collect_types(node["@graph"], out)


def parse_on_page(html: str) -> dict:
    strip = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
    title_m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, re.I)
    title = strip(title_m.group(1)) if title_m else ""
    meta = _tag(r"""<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["'][^>]*>""",
                r"""<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["'][^>]*>""", html)
    canonical = _tag(r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["'][^>]*>""",
                     r"""<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["'][^>]*>""", html)
    og = _tag(r"""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']*)["'][^>]*>""",
              r"""<meta[^>]+content=["']([^"']*)["'][^>]+property=["']og:title["'][^>]*>""", html)
    types: list = []
    for m in re.finditer(r"""<script[^>]+type=["']application/ld\+json["'][^>]*>([\s\S]*?)</script>""", html, re.I):
        try:
            _collect_types(json.loads(m.group(1).strip()), types)
        except ValueError:
            pass
    return {"title": title, "titleLen": len(title), "meta": meta, "metaLen": len(meta), "h1Count": len(re.findall(r"<h1\b[^>]*>", html, re.I)),
            "canonical": canonical or None, "ogTitle": og or None, "schemaTypes": list(dict.fromkeys(types))[:40]}


async def analyse_sitemap(origin: str, hints, fetch) -> dict:
    candidates = []
    for hint in hints or []:
        try:
            candidates.append(urljoin(origin, hint))
        except ValueError:
            pass
    candidates += [origin + "/sitemap.xml", origin + "/sitemap_index.xml"]
    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = await fetch(url, "application/xml,text/xml,*/*")
            if not r.ok or not re.search(r"<urlset|<sitemapindex", r.text, re.I):
                continue
            if re.search(r"<sitemapindex", r.text, re.I):
                locs = [m.strip() for m in re.findall(r"<loc>\s*([^<]+)\s*</loc>", r.text, re.I)]
                count = min(len(locs), 200)
                if locs:
                    try:
                        child = await fetch(locs[0], "application/xml,text/xml,*/*")
                        if child.ok:
                            count = min(len(re.findall(r"<url\b", child.text, re.I)) + max(0, len(locs) - 1), 200)
                    except Exception:
                        pass
                return {"found": True, "url": r.final_url or url, "urlCount": count, "note": "sitemap index"}
            return {"found": True, "url": r.final_url or url, "urlCount": min(len(re.findall(r"<url\b", r.text, re.I)), 200)}
        except Exception:
            continue
    return {"found": False, "url": None, "urlCount": 0, "error": "not_found"}


async def run_psi(url: str, key, client: httpx.AsyncClient | None = None) -> dict:
    key = (key or "").strip()
    if not key:
        return {"available": False, "note": "PAGESPEED_API_KEY not set — open PageSpeed Insights UI (link below)."}
    params = [("url", url), ("strategy", "mobile"), ("category", "PERFORMANCE"), ("category", "SEO"),
              ("category", "ACCESSIBILITY"), ("category", "BEST_PRACTICES"), ("key", key)]
    owns = client is None
    client = client or httpx.AsyncClient(timeout=PSI_TIMEOUT)
    try:
        r = await client.get("https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed",
                             params=params, headers={"x-goog-api-key": key})
        if r.status_code >= 400:
            detail = ""
            try:
                err = r.json().get("error", {})
                reasons = [str(d["reason"]) for d in (err.get("details") or []) + (err.get("errors") or []) if isinstance(d, dict) and d.get("reason")]
                detail = " | ".join(x for x in [err.get("status", ""), err.get("message", ""), ",".join(reasons)] if x)
                detail = detail.replace(key, "[REDACTED]")
            except Exception:
                pass
            return {"available": False, "note": f"PageSpeed API returned HTTP {r.status_code}" + (f" — {detail}" if detail else ""), "strategy": "mobile"}
        data = r.json()
        cats = (data.get("lighthouseResult") or {}).get("categories") or {}
        audits = (data.get("lighthouseResult") or {}).get("audits") or {}
        metrics = (data.get("loadingExperience") or {}).get("metrics") or {}
        score = lambda c: round(c["score"] * 100) if isinstance(c, dict) and isinstance(c.get("score"), (int, float)) else None
        pct = lambda name: (metrics.get(name) or {}).get("percentile")
        lcp, inp, cls = pct("LARGEST_CONTENTFUL_PAINT_MS"), pct("INTERACTION_TO_NEXT_PAINT"), pct("CUMULATIVE_LAYOUT_SHIFT_SCORE")
        return {"available": True, "strategy": "mobile", "performance": score(cats.get("performance")), "seo": score(cats.get("seo")),
                "accessibility": score(cats.get("accessibility")), "bestPractices": score(cats.get("best-practices")),
                "lcp": f"{lcp / 1000:.1f}s" if lcp is not None else (audits.get("largest-contentful-paint") or {}).get("displayValue"),
                "inp": f"{round(inp)}ms" if inp is not None else None,
                "cls": f"{cls / 100:.2f}" if cls is not None else (audits.get("cumulative-layout-shift") or {}).get("displayValue")}
    except Exception as error:  # never leak the key through an exception message
        return {"available": False, "note": f"PageSpeed request failed ({error_name(error)})", "strategy": "mobile"}
    finally:
        if owns:
            await client.aclose()


def build_buckets(https, status, robots, sitemap, on_page, psi) -> dict:
    g, b = robots["googlebot"], robots["bingbot"]
    indexed = "amber"
    if not https or status >= 400 or status == 0 or g == "blocked" or b == "blocked":
        indexed = "red"
    elif g in ("allowed", "unknown") and b in ("allowed", "unknown") and sitemap["found"]:
        indexed = "green"
    found = "amber"
    if not on_page["title"]:
        found = "red"
    elif 15 <= on_page["titleLen"] <= 60 and 50 <= on_page["metaLen"] <= 160 and on_page["h1Count"] == 1:
        found = "green"
    if psi.get("available") and isinstance(psi.get("performance"), (int, float)) and psi["performance"] < 50 and found == "green":
        found = "amber"
    return {"indexed": indexed, "found": found, "mentioned": "unknown"}


def build_links(url: str, host: str) -> dict:
    e, bare = quote(url, safe="-_.!~*'()"), re.sub(r"^www\.", "", host)
    return {"psi": "https://pagespeed.web.dev/analysis?url=" + e, "rrt": "https://search.google.com/test/rich-results?url=" + e,
            "gsc": "https://search.google.com/search-console", "ga4": "https://analytics.google.com/",
            "bing": "https://www.bing.com/webmasters", "ahrefs": "https://ahrefs.com/backlink-checker?input=" + quote(bare, safe="-_.!~*'()"),
            "semrush": "https://www.semrush.com/", "answerThePublic": "https://answerthepublic.com/", "trends": "https://trends.google.com/",
            "similarWeb": "https://chromewebstore.google.com/detail/similarweb-traffic-rank-w/hoklmmgfncapjnnelbajcjehmjhikoii",
            "schemaValidator": "https://validator.schema.org/"}


async def site_check(raw_url, pagespeed_key=None, client: httpx.AsyncClient | None = None, psi_client=None) -> dict:
    target = normalise(raw_url, keep_path=True)
    warnings: list = []

    async def fetch(url, accept):
        return await fetch_text(url, accept=accept, ua=SITE_UA, timeout=SITE_TIMEOUT, max_bytes=SITE_MAX_BYTES, client=client)

    https, status, final = target["origin"].startswith("https:"), 0, target["href"]
    x_robots = None
    on_page = {"title": "", "titleLen": 0, "meta": "", "metaLen": 0, "h1Count": 0, "canonical": None, "ogTitle": None}
    schema_types: list = []
    try:
        page = await fetch(target["href"], "text/html,*/*")
        status, final = page.status, page.final_url or target["href"]
        https = final.startswith("https:")
        x_robots = page.headers.get("x-robots-tag")
        if page.text:
            parsed = parse_on_page(page.text)
            schema_types = parsed.pop("schemaTypes")
            on_page = parsed
        if not page.ok:
            warnings.append(f"Page returned HTTP {page.status}")
    except (ToolError, ValueError, httpx.HTTPError, asyncio.TimeoutError) as error:
        warnings.append(f"Could not fetch page ({error_name(error)})")
        status = 0
    robots = {key: "unknown" for key, _, _ in AI_BOTS}
    hints: list = []
    try:
        r = await fetch(target["origin"] + "/robots.txt", "text/plain,*/*")
        if r.ok:
            robots, hints = analyse_robots(r.text)
        else:
            warnings.append(f"robots.txt HTTP {r.status}")
    except (ToolError, ValueError, httpx.HTTPError, asyncio.TimeoutError):
        warnings.append("robots.txt fetch failed")
    try:
        sitemap = await analyse_sitemap(target["origin"], hints, fetch)
    except Exception:
        sitemap = {"found": False, "url": None, "urlCount": 0, "error": "error"}
    llms = {"found": False, "note": "Optional file; Google Search ignores llms.txt for rankings and AI Overviews."}
    try:
        r = await fetch(target["origin"] + "/llms.txt", "text/plain,*/*")
        if r.ok and r.text.strip():
            llms = {"found": True, "note": llms["note"]}
    except Exception:
        pass
    psi = await run_psi(final or target["href"], pagespeed_key, psi_client)
    types_lower = [t.lower() for t in schema_types]
    return {
        "mode": "server", "url": final or target["href"], "origin": target["origin"], "https": https, "status": status,
        "xRobotsTag": x_robots, "robots": robots, "sitemap": sitemap, "llmsTxt": llms, "onPage": on_page, "schemaTypes": schema_types,
        "missingCommonSchema": [t for t in ("Organization", "WebSite", "Service") if t.lower() not in types_lower],
        "psi": psi, "buckets": build_buckets(https, status, robots, sitemap, on_page, psi), "links": build_links(final or target["href"], urlsplit(target["origin"]).hostname or ""),
        "warnings": warnings,
        "honesty": "Public technical snapshot only — not your Google rankings. Mentions in AI answers are not checked here. No ranking promises.",
    }


def pagespeed_key() -> str | None:
    return os.environ.get("PAGESPEED_API_KEY")
