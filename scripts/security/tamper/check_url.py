#!/usr/bin/env python3
"""Check a URL before it goes on trendibizz.com or before a bot follows it.

  bash scripts/security/check-url.sh <url> [--json] [--no-fetch]

Checks (no paid API, no key needed):
  1. Shape: https only, no user@host trick, no bare IP, no punycode lookalike
     (flagged), no executable/archive download.
  2. Threat lists: URLhaus mirror, phishing feeds, OpenPhish, local blocklist
     (+ Google Safe Browsing / URLhaus API if a key is configured).
  3. DNS: the host resolves, and not to a private/internal address.
  4. Domain age + expiry via RDAP (free; .com/.org/.ai/.dev etc. — .nz has no
     public RDAP, so age shows "unknown" there).
  5. Redirects: follows up to 10 hops by hand (HEAD, then GET), re-checking each
     hop; flags a hop to a different site, an http:// downgrade, or a final 4xx/5xx.

Exit: 0 PASS · 3 REVIEW (warnings, a human should look) · 1 FAIL (do not use/follow)
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from threatlist import ThreatList, keyed_lookups  # noqa: E402

UA = "Mozilla/5.0 (compatible; TrendiLinkCheck/1.0; +https://trendibizz.com/security)"
EXEC_EXT = (".exe", ".msi", ".apk", ".dmg", ".pkg", ".zip", ".rar", ".7z", ".jar", ".scr", ".bat", ".cmd",
            ".ps1", ".vbs", ".js", ".hta", ".iso", ".img", ".lnk", ".docm", ".xlsm", ".sh")
SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly", "cutt.ly",
              "shorturl.at", "rb.gy", "t.ly", "lnkd.in", "tiny.cc", "s.id", "v.gd", "qr.ae"}
MULTI_SUFFIX = {"co.nz", "org.nz", "net.nz", "govt.nz", "ac.nz", "school.nz", "geek.nz", "kiwi.nz", "co.uk",
                "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "edu.au", "gov.au", "co.jp", "com.br",
                "co.in", "co.za", "com.sg", "com.cn"}


def site_of(host: str) -> str:
    labels = host.lower().strip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in MULTI_SUFFIX:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")  # sandbox/proxy "fake-IP" DNS answers


def resolve(host: str):
    """Real public DNS answer. Uses Cloudflare DNS-over-HTTPS (free, no key) so a
    proxy that fakes local DNS (e.g. this box answers 198.18.0.1 for everything)
    cannot hide a dead domain. Returns (set_of_ips | None, method)."""
    ips, rcode = set(), None
    for typ in ("A", "AAAA"):
        try:
            req = urllib.request.Request(f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(host)}&type={typ}",
                                         headers={"Accept": "application/dns-json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.load(r)
            rcode = d.get("Status", rcode)
            for a in d.get("Answer", []) or []:
                if a.get("type") in (1, 28):
                    ips.add(a["data"])
        except Exception:
            rcode = rcode if rcode is not None else -1
    if ips or rcode in (0, 3):
        return ips, "Cloudflare DoH"
    try:
        sys_ips = {ai[4][0] for ai in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
        sys_ips = {a for a in sys_ips if ipaddress.ip_address(a) not in FAKE_IP_NET}
        return (sys_ips or None), "system resolver"
    except socket.gaierror:
        return set(), "system resolver"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def one_hop(url: str):
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            r = OPENER.open(req, timeout=15)
            status, headers = r.status, r.headers
            if method == "GET":
                r.read(65536)
            r.close()
        except urllib.error.HTTPError as e:
            status, headers = e.code, e.headers
        if method == "HEAD" and status >= 400:
            continue
        return status, headers
    return status, headers


def rdap(host: str):
    dom = site_of(host)
    try:
        req = urllib.request.Request(f"https://rdap.org/domain/{dom}", headers={"User-Agent": UA, "Accept": "application/rdap+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            tld = dom.rsplit(".", 1)[-1]
            return dom, None, None, f"no public RDAP for .{tld} (or not registered)"
        return dom, None, None, f"RDAP HTTP {e.code}"
    except Exception as e:
        return dom, None, None, f"RDAP unavailable ({e.__class__.__name__})"
    reg = exp = None
    for ev in d.get("events", []):
        a, when = ev.get("eventAction"), ev.get("eventDate", "")
        try:
            t = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            continue
        if a == "registration":
            reg = t
        elif a == "expiration":
            exp = t
    return dom, reg, exp, None


def check(url: str, fetch: bool = True, tl: ThreatList | None = None) -> dict:
    res = {"url": url, "fail": [], "warn": [], "info": [], "hops": []}
    F, W, I = res["fail"].append, res["warn"].append, res["info"].append
    tl = tl or ThreatList()
    for n in tl.notes:
        (W if n.startswith("WARN") else I)(n.split("  ", 1)[-1])
    try:
        u = urllib.parse.urlsplit(url.strip())
    except ValueError:
        F("not a valid URL")
        return res
    if u.scheme != "https":
        F(f"scheme is '{u.scheme or '(none)'}' — only https:// links are allowed")
        if u.scheme not in ("http",):
            return res
    host = (u.hostname or "").lower()
    if not host:
        F("no host")
        return res
    if "@" in u.netloc:
        F("URL contains user@host — classic phishing disguise (the real host is after the @)")
    try:
        ipaddress.ip_address(host.strip("[]"))
        F("host is a bare IP address")
    except ValueError:
        pass
    if "xn--" in host:
        W(f"punycode host {host} — check for a lookalike of a real brand (homograph)")
    if host in SHORTENERS or site_of(host) in SHORTENERS:
        W("link shortener — expand it and check the destination instead")
    if u.path.lower().endswith(EXEC_EXT):
        F(f"path ends in an executable/archive extension ({u.path[-12:]})")
    allowed = set()
    ap = HERE / "allowed-domains.txt"
    if ap.exists():
        allowed = {l.split("#")[0].strip().lower() for l in ap.read_text().splitlines() if l.split("#")[0].strip()}
    I(f"{host} is {'ON' if host in allowed else 'NOT on'} the site allowlist")

    hit = tl.check_url(url) or tl.check_host(host)
    if hit:
        F(f"on threat list: {hit}")
    else:
        I("not on threat lists (" + ", ".join(tl.loaded) + ")")

    addrs, how = resolve(host)
    res["dns"] = sorted(addrs)
    if addrs is None:
        W(f"could not check DNS for {host}")
        res["dns"] = None
    elif not addrs:
        F(f"{host} does not resolve (dead or expired domain — could be re-registered by anyone)")
    else:
        I(f"DNS ({how}): {', '.join(sorted(addrs)[:4])}")
        for a in addrs:
            ip = ipaddress.ip_address(a)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                F(f"resolves to non-public address {a}")

    dom, reg, exp, err = rdap(host)
    now = dt.datetime.now(dt.timezone.utc)
    res["registrable"] = dom
    if err:
        W(f"domain age unknown: {err}") if not dom.endswith(".nz") else I(f"domain age unknown: {err}")
    else:
        if reg:
            age = (now - reg).days
            res["age_days"] = age
            I(f"{dom} registered {reg.date()} ({age} days ago)")
            if age < 30:
                F(f"domain is only {age} days old — very common for phishing/malware")
            elif age < 180:
                W(f"domain is young ({age} days)")
        if exp:
            res["expires"] = exp.date().isoformat()
            left = (exp - now).days
            if left < 0:
                F(f"domain registration expired {exp.date()} — could be bought by anyone")
            elif left < 30:
                W(f"domain expires in {left} days ({exp.date()})")
            else:
                I(f"expires {exp.date()}")

    if fetch and res.get("dns") and u.scheme == "https":
        cur = url
        start_site = site_of(host)
        for _ in range(10):
            try:
                status, headers = one_hop(cur)
            except Exception as e:
                W(f"fetch failed at {cur[:80]}: {e.__class__.__name__}: {str(e)[:80]}")
                break
            res["hops"].append({"url": cur, "status": status})
            if status in (301, 302, 303, 307, 308) and headers.get("Location"):
                nxt = urllib.parse.urljoin(cur, headers["Location"])
                nu = urllib.parse.urlsplit(nxt)
                if nu.scheme != "https":
                    F(f"redirect downgrades to {nu.scheme}:// ({nxt[:80]})")
                nh = (nu.hostname or "").lower()
                if nh and site_of(nh) != start_site:
                    W(f"redirects to a different site: {nh}")
                    h2 = tl.check_url(nxt) or tl.check_host(nh)
                    if h2:
                        F(f"redirect target on threat list: {h2}")
                cur = nxt
                continue
            ctype = (headers.get("Content-Type") or "").lower()
            disp = (headers.get("Content-Disposition") or "").lower()
            if any(x in ctype for x in ("application/x-msdownload", "application/x-dosexec", "application/vnd.android.package", "application/x-sh")) or (
                    "attachment" in disp and any(disp.rstrip('"').endswith(e) for e in EXEC_EXT)):
                F(f"final URL serves a download ({ctype or disp})")
            if status >= 400:
                (I if status in (401, 403, 429, 999) else W)(f"final status HTTP {status}" + (" (site blocks bots — usually fine in a browser)" if status in (401, 403, 429, 999) else " — dead link?"))
            else:
                I(f"final status HTTP {status} at {cur[:100]}")
            break
        else:
            W("more than 10 redirects")
        res["final"] = cur
        if urllib.parse.urlsplit(cur).hostname and cur != url:
            hit2 = tl.check_url(cur)
            if hit2:
                F(f"final URL on threat list: {hit2}")

    hits, notes = keyed_lookups([url] + ([res["final"]] if res.get("final") and res["final"] != url else []))
    for n in notes:
        (W if n.startswith("WARN") else I)(n.split("  ", 1)[-1])
    for k, v in hits.items():
        F(f"{v}: {k}")
    res["verdict"] = "FAIL" if res["fail"] else ("REVIEW" if res["warn"] else "PASS")
    return res


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    as_json = "--json" in argv
    tl = ThreatList(offline="--offline" in argv)
    worst = 0
    out = []
    for url in args:
        r = check(url, fetch="--no-fetch" not in argv, tl=tl)
        out.append(r)
        worst = max(worst, {"PASS": 0, "REVIEW": 3, "FAIL": 4}[r["verdict"]])
        if not as_json:
            print(f"== {r['verdict']}  {url}")
            for f in r["fail"]:
                print(f"   FAIL  {f}")
            for w in r["warn"]:
                print(f"   WARN  {w}")
            for i in r["info"]:
                print(f"   info  {i}")
            if r["hops"]:
                print("   hops  " + " -> ".join(f"{h['status']} {h['url'][:70]}" for h in r["hops"]))
    if as_json:
        print(json.dumps(out, indent=2, default=str))
    return {0: 0, 3: 3, 4: 1}[worst]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
