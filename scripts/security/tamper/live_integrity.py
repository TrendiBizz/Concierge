#!/usr/bin/env python3
"""Daily tamper check: is live trendibizz.com exactly what we deployed?

Compares every path in deploy_known_good/manifest.json (byte-for-byte, sha256)
and the security headers in deploy_known_good/headers.txt against what
https://trendibizz.com serves right now, plus a few redirect/status probes.

  bash scripts/security/live-integrity.sh [--base https://trendibizz.com] [--known-good DIR]

Exit 0 = PASS, 1 = TAMPER/MISMATCH (report written), 2 = could not run (network).
Report: scripts/security/reports/live-integrity-<NZ time>.txt (+ latest.txt)
Cost: ~60 GETs, ~13 MB, ~10-20 s. No keys, no accounts.
"""
from __future__ import annotations

import os
import argparse
import base64
import concurrent.futures as cf
import datetime as dt
import difflib
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The central repo is the site source (website/) and therefore the known-good.
# TRENDI_SITE_ROOT keeps the old trendi-site checkout usable for comparison.
ROOT = Path(os.environ.get("TRENDI_SITE_ROOT", str(HERE.parents[2])))
if not ROOT.is_dir():
    ROOT = HERE.parents[2]
REPORTS = Path(os.environ.get("TRENDI_TAMPER_REPORTS", str(HERE / "reports")))
UA = "TrendiIntegrityCheck/1.0 (+https://trendibizz.com/.well-known/security.txt)"
SEC_HEADERS = ["strict-transport-security", "x-content-type-options", "x-frame-options", "referrer-policy",
               "permissions-policy", "cross-origin-opener-policy", "cross-origin-resource-policy",
               "content-security-policy", "x-robots-tag"]
NZ = dt.timezone(dt.timedelta(hours=13))  # NZDT; label only


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(url: str, method: str = "GET", read: bool = True):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept-Encoding": "identity", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                                              "Cache-Control": "no-cache"})
    try:
        r = OPENER.open(req, timeout=30)
        body = r.read() if read else b""
        return r.status, r.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, (e.read() if read else b"")


def url_for(path: str) -> str:
    """Cloudflare Pages pretty URLs: /x.html -> /x, /index.html -> /, /d/index.html -> /d/."""
    if path.endswith("/index.html"):
        return path[: -len("index.html")]
    if path.endswith(".html"):
        return path[:-5]
    return path


def parse_headers_file(text: str):
    rules, cur = [], None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            cur = (line.strip(), {})
            rules.append(cur)
        elif cur and ":" in line:
            k, v = line.strip().split(":", 1)
            k = k.strip().lower()
            if k.startswith("! "):
                continue
            cur[1][k] = v.strip()
    return rules


def expected_headers(rules, path: str) -> dict:
    out = {}
    for pat, hdrs in rules:
        rx = "^" + re.escape(pat).replace(r"\*", ".*").replace(r"\:splat", ".*") + "$"
        if re.match(rx, path):
            out.update(hdrs)
    return out


def norm(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip()).rstrip(";").lower()


def norm_header(name: str, value: str) -> str:
    """Normalise a header for comparison. Cloudflare's bot-management injection
    adds a literal 'nonce-{CSP_NONCE}' source to script-src; it is an edge
    transform, not a site change, so it must not raise a tamper alarm."""
    v = norm(value)
    if name == "content-security-policy":
        v = v.replace(" 'nonce-{csp_nonce}'", "")
    return v


CF_BEACON_RE = re.compile(rb"""<script type="module" src="https://static\.cloudflareinsights\.com/beacon\.min\.js/v[0-9a-f]{10,80}" integrity="sha512-[A-Za-z0-9+/=]{80,90}" data-cf-beacon='(\{[^'<>]{0,300}\})' crossorigin="anonymous"></script>""")
# Cloudflare injects its bot-management loader into some HTML responses. It is
# infrastructure, not site content; strip only the exact known shape.
CF_CHALLENGE_RE = re.compile(
    rb"""<script>\(function\(\)\{function c\(\)\{var b=a\.contentDocument.*?__CF\$cv\$params.*?\}\)\(\);</script>""",
    re.S)


def beacon_tokens() -> set:
    f = HERE / "cf-beacon.txt"
    if not f.exists():
        return set()
    return {l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")}


def strip_cf_beacon(body: bytes, expected: bytes):
    """Return (body_without_beacon, note). Only the exact Cloudflare Web Analytics
    tag with our pinned token is removed; anything else is left in (and fails)."""
    ms = list(CF_BEACON_RE.finditer(body))
    if len(ms) != 1 or CF_BEACON_RE.search(expected):
        return body, None
    m = ms[0]
    try:
        tok = json.loads(m.group(1)).get("token", "")
    except ValueError:
        return body, "cf-beacon: unparsable data-cf-beacon"
    if tok not in beacon_tokens():
        return body, f"cf-beacon token {tok!r} is not ours (scripts/security/cf-beacon.txt) — analytics hijack?"
    for a, b in ((m.start(), m.end() + 1), (m.start() - 1, m.end()), (m.start(), m.end())):
        cand = body[:max(a, 0)] + body[b:]
        if cand == expected:
            return cand, None
    return body[:m.start()] + body[m.end():], None


def strip_cf_challenge(body: bytes, expected: bytes):
    """Remove Cloudflare's injected challenge-platform loader if it is not in the
    deployed file. Only the fixed loader shape is removed; a challenge *page*
    (which replaces the body) still fails the hash check."""
    if CF_CHALLENGE_RE.search(expected):
        return body, None
    ms = list(CF_CHALLENGE_RE.finditer(body))
    if not ms:
        return body, None
    for m in ms:
        for a, b in ((m.start(), m.end() + 1), (m.start() - 1, m.end()), (m.start(), m.end())):
            cand = body[:max(a, 0)] + body[b:]
            if cand == expected:
                return cand, None
    out = body
    for m in reversed(ms):
        out = out[:m.start()] + out[m.end():]
    return out, None


def hosts_in(b: bytes) -> set:
    return {h.lower() for h in re.findall(rb"https?://([A-Za-z0-9.-]+)", b) for h in [h.decode()]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://trendibizz.com")
    ap.add_argument("--known-good", default=str(ROOT / "deploy_known_good"))
    ap.add_argument("--site", help="build the expected state from this site source tree (e.g. website/) instead of a deploy_known_good snapshot")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    # With no explicit baseline choice, compare against the repo's website/ tree.
    if a.site is None and a.known_good == str(ROOT / "deploy_known_good") and (ROOT / "website").is_dir():
        a.site = str(ROOT / "website")
    kg = Path(a.known_good)
    base = a.base.rstrip("/")
    lines, fails, warns = [], [], []

    def F(msg):
        fails.append(msg); lines.append("FAIL  " + msg)

    def W(msg):
        warns.append(msg); lines.append("WARN  " + msg)

    def P(msg):
        lines.append("ok    " + msg)

    if a.site:
        site = Path(a.site).resolve()
        if not (site / "index.html").is_file():
            print(f"LIVE-INTEGRITY: ERROR --site {site} has no index.html")
            return 2
        manifest, assets = {}, {}
        for p in sorted(site.rglob("*")):
            rel = p.relative_to(site)
            if (not p.is_file() or any(part.startswith(".") and part not in (".well-known",) for part in rel.parts)
                    or rel.name.startswith("._") or rel.as_posix() in ("_headers", "_redirects")):
                continue
            key = "/" + rel.as_posix()
            body = p.read_bytes()
            manifest[key] = hashlib.sha256(body).hexdigest()
            assets[manifest[key]] = body
        headers_p = site / "_headers"
        rules = parse_headers_file(headers_p.read_text()) if headers_p.is_file() else []
        try:
            dep = subprocess.run(["git", "-C", str(site), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            dep = "working-tree"
        dep = f"repo {dep} ({site.name}/)"
    else:
        manifest = json.loads((kg / "manifest.json").read_text())
        assets = {x["key"]: x["value"] for x in json.loads((kg / "all_assets.json").read_text())}
        dep = (kg / "deployment_id.txt").read_text().strip() if (kg / "deployment_id.txt").exists() else "?"
        rules = parse_headers_file((kg / "headers.txt").read_text())
    now = dt.datetime.now(NZ).strftime("%Y-%m-%d %H:%M NZDT")
    lines.append(f"=== Trendi live integrity === {now}  base={base}  known-good deployment={dep}  paths={len(manifest)}")

    # network sanity
    try:
        st, _, _ = get(base + "/robots.txt", read=False, method="HEAD")
    except Exception as e:
        print(f"LIVE-INTEGRITY: ERROR cannot reach {base} ({e.__class__.__name__}: {e})")
        return 2

    def check_path(item):
        path, h = item
        exp = assets.get(h) if h in assets else None
        if isinstance(exp, str):
            exp = base64.b64decode(exp)
        url = base + urllib.parse.quote(url_for(path))
        try:
            st, hd, body = get(url)
        except Exception as e:
            return path, url, None, None, None, exp, f"{e.__class__.__name__}: {e}"
        return path, url, st, hd, body, exp, None

    results = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(check_path, sorted(manifest.items())))

    ok_files = 0
    for path, url, st, hd, body, exp, err in results:
        if err:
            # one retry, sequential (propagation / transient)
            path, url, st, hd, body, exp, err = check_path((path, manifest[path]))
            if err:
                F(f"{url_for(path)}: fetch error {err}")
                continue
        if exp is None:
            F(f"{path}: hash {manifest[path]} not in all_assets.json (baseline incomplete)")
            continue
        if st != 200 and not (path == "/404.html" and st == 404):
            loc = hd.get("Location", "") if hd else ""
            F(f"{url_for(path)}: HTTP {st}{' -> ' + loc if loc else ''} (expected 200; unexpected redirect/status)")
            continue
        if path.endswith(".html"):
            body, bnote = strip_cf_beacon(body, exp)
            if bnote:
                F(f"{url_for(path)}: {bnote}")
            body, _ = strip_cf_challenge(body, exp)
        if hashlib.sha256(body).digest() != hashlib.sha256(exp).digest():
            new_hosts = sorted(hosts_in(body) - hosts_in(exp))
            new_scripts = sorted(set(re.findall(rb"<script\b[^>]*>", body, re.I)) - set(re.findall(rb"<script\b[^>]*>", exp, re.I)))
            F(f"{url_for(path)}: CONTENT CHANGED (live {len(body)} B sha256 {hashlib.sha256(body).hexdigest()[:12]} vs deployed {len(exp)} B {hashlib.sha256(exp).hexdigest()[:12]})"
              + (f"; NEW HOSTS: {', '.join(new_hosts)}" if new_hosts else "")
              + (f"; NEW <script> TAGS: {[s.decode('utf-8','replace')[:100] for s in new_scripts]}" if new_scripts else ""))
            try:
                d = list(difflib.unified_diff(exp.decode("utf-8").splitlines(), body.decode("utf-8").splitlines(), "deployed", "live", n=0, lineterm=""))
                for dl in d[:30]:
                    lines.append("        " + dl[:200])
            except UnicodeDecodeError:
                lines.append("        (binary file)")
            continue
        # headers
        exph = expected_headers(rules, url_for(path)) or {}
        exph2 = expected_headers(rules, path)
        exph = {**exph2, **exph}
        bad = False
        for k in SEC_HEADERS:
            want, got = exph.get(k), hd.get(k)
            if want is None:
                if k == "x-robots-tag" and got:
                    W(f"{url_for(path)}: unexpected X-Robots-Tag '{got}' (not in headers.txt)")
                continue
            if norm_header(k, want) != norm_header(k, got or ""):
                F(f"{url_for(path)}: header {k} live={got!r} expected={want!r}")
                bad = True
        ct_want = exph.get("content-type")
        if ct_want and norm(ct_want).split(";")[0] != norm(hd.get("content-type", "")).split(";")[0]:
            F(f"{url_for(path)}: Content-Type live={hd.get('content-type')!r} expected={ct_want!r}")
            bad = True
        if not bad:
            ok_files += 1
    P(f"{ok_files}/{len(manifest)} files byte-identical to deployment {dep} with expected security headers")

    # status / redirect probes
    probes = [
        ("https://www.trendibizz.com/", (301, 308), "https://trendibizz.com/"),
        (base + "/shop", (410,), None),
        (base + "/wp-login.php", (410,), None),
        (base + "/tools/security-check", (301, 308), "/security-check"),
        (base + "/_headers", (404,), None),
        (base + "/_redirects", (404,), None),
        (base + "/_worker.js", (404,), None),
        (base + "/.git/config", (404,), None),
        (base + "/integrity-probe-does-not-exist-7f3a", (404,), None),
    ]
    for url, codes, loc in probes:
        try:
            st, hd, body = get(url)
        except Exception as e:
            W(f"probe {url}: {e.__class__.__name__}")
            continue
        got_loc = hd.get("Location", "") if hd else ""
        if st not in codes:
            F(f"probe {url}: HTTP {st}{' -> ' + got_loc if got_loc else ''} (expected {codes})")
        elif loc and not (got_loc == loc or got_loc.endswith(loc) and (got_loc.startswith("/") or got_loc.startswith("https://trendibizz.com"))):
            F(f"probe {url}: redirects to {got_loc!r} (expected {loc!r}) — UNEXPECTED REDIRECT")
        else:
            P(f"probe {url}: {st}{' -> ' + got_loc if got_loc else ''}")
        if st in (301, 302, 303, 307, 308) and got_loc:
            h = (urllib.parse.urlsplit(urllib.parse.urljoin(url, got_loc)).hostname or "").lower()
            if h not in ("trendibizz.com", "www.trendibizz.com"):
                F(f"probe {url}: redirects OFF-SITE to {h}")
    # http -> https (port 80; some sandboxes cannot reach it)
    try:
        st, hd, _ = get("http://trendibizz.com/", read=False)
        loc = hd.get("Location", "") if hd else ""
        if st in (301, 308) and loc.startswith("https://trendibizz.com"):
            P(f"probe http://trendibizz.com/: {st} -> {loc}")
        elif st >= 500 and "pingora" in (hd.get("Server", "") if hd else "").lower():
            lines.append("skip  http://trendibizz.com/ (port 80 not reachable from this machine)")
        else:
            F(f"probe http://trendibizz.com/: HTTP {st} -> {loc!r} (expected 301/308 to https://trendibizz.com)")
    except Exception as e:
        lines.append(f"skip  http://trendibizz.com/ ({e.__class__.__name__})")

    verdict = "FAIL" if fails else "PASS"
    lines.append(f"LIVE-INTEGRITY: {verdict}  (fail={len(fails)} warn={len(warns)})")
    if fails:
        lines.append("  If nobody deployed just now: treat as possible tampering. Compare website/ with the deploy "
                     "manifest on the box, rotate the Cloudflare API token if unexplained, and tell Jo.")
        lines.append("  If a deploy just happened: run scripts/vps/verify-deploy.sh, then re-run this check.")
    report = "\n".join(lines) + "\n"
    print(report, end="")
    rd = REPORTS
    rd.mkdir(exist_ok=True)
    stamp = dt.datetime.now(NZ).strftime("%Y%m%d-%H%M")
    (rd / f"live-integrity-{stamp}.txt").write_text(report)
    (rd / "live-integrity-latest.txt").write_text(report)
    # keep 30 newest
    old = sorted(rd.glob("live-integrity-2*.txt"))[:-30]
    for o in old:
        o.unlink()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
