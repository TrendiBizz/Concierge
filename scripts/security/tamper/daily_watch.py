#!/usr/bin/env python3
"""daily_watch.py: READ-ONLY daily tamper and unexpected-change watch for trendibizz.com.

Never writes to Cloudflare, DNS or the site. Network use is HTTP GET only:
  - live_integrity.py (GETs of trendibizz.com)
  - Cloudflare DNS-over-HTTPS (public DNS), crt.sh / Cert Spotter, Verisign RDAP
  - an `openssl s_client` handshake to trendibizz.com:443 (TLS version probe)
Cloudflare account state comes from a snapshot file produced by cf-snapshot.js
(run through the Cloudflare MCP, GET only); see README.md section 5.

Exit: 0 all clear · 1 change or problem found · 2 could not check something (and nothing changed)
"""
import argparse, datetime as dt, difflib, hashlib, json, os, re, shutil, subprocess, sys, time
import urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The central repo is the site source (website/) and the deploy ledger. TRENDI_SITE_ROOT
# keeps the old trendi-site checkout usable for comparison.
ROOT = Path(os.environ.get("TRENDI_SITE_ROOT", str(HERE.parents[2])))
if not (ROOT / "website").is_dir() and (Path.home() / "OpenBot/Shared/trendi-site").is_dir():
    ROOT = Path.home() / "OpenBot/Shared/trendi-site"
REPORTS = HERE / "reports"
STATE = REPORTS / "daily-watch-state"           # last run's observed state (what `accept` copies)
DEFAULT_BASELINES = HERE / "baselines"
DOMAIN = "trendibizz.com"
UA = "trendi-daily-watch/1 (+https://trendibizz.com/security-check; read-only)"
NZ = dt.timezone(dt.timedelta(hours=13))  # NZDT; label printed explicitly

CF_SECTIONS = ["dns", "dnssec", "zone", "zone_settings", "rulesets", "worker_scripts", "worker",
               "worker_routes", "members", "account", "notifications", "page_shield", "pages_project"]
OTHER_SECTIONS = ["public_dns", "rdap", "certs", "deployments"]
ALL_SECTIONS = CF_SECTIONS + OTHER_SECTIONS
LABELS = {
    "dns": "Cloudflare DNS records", "dnssec": "DNSSEC", "zone": "Zone (nameservers/plan/status)",
    "zone_settings": "Zone settings (SSL mode, min TLS, HSTS, ...)", "rulesets": "WAF / rulesets",
    "worker_scripts": "Account Worker scripts", "worker": "trendi-force-https Worker source hash",
    "worker_routes": "Worker routes", "members": "Account members and roles",
    "account": "Account 2FA settings", "notifications": "Cloudflare notification policies",
    "page_shield": "Client-side security (Page Shield)", "pages_project": "Pages project config",
    "public_dns": "Public DNS + TLS view (DoH, openssl)", "rdap": "Registrar lock / expiry (RDAP)",
    "certs": "Certificate Transparency (new certificates)", "deployments": "Pages deployments vs changes.csv",
}

def now_nz():
    return dt.datetime.now(NZ)

def fmt_nz(t):
    return t.astimezone(NZ).strftime("%Y-%m-%d %H:%M NZDT")

def http_get(url, timeout=25, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def get_json(url, tries=2, timeout=25, accept="application/json"):
    last = None
    for i in range(tries):
        try:
            st, body = http_get(url, timeout, accept)
            return json.loads(body)
        except Exception as e:  # noqa
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"{url.split('?')[0]}: {type(last).__name__}: {str(last)[:120]}")

def canon(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

# ---------------------------------------------------------------- collectors
def load_cf_snapshot(path, max_age_min):
    """Returns (snapshot dict | None, problem str | None)."""
    if not path:
        return None, "no --cf-snapshot given (Cloudflare account state not checked)"
    p = Path(path)
    if not p.is_file():
        return None, f"snapshot file not found: {p}"
    text = p.read_text(errors="replace")
    i = text.find("{")
    if i < 0:
        return None, "snapshot file has no JSON"
    try:
        snap, _ = json.JSONDecoder().raw_decode(text[i:])
    except Exception as e:
        return None, f"snapshot JSON unreadable: {e}"
    if snap.get("tool") != "cf-snapshot.js":
        return None, "snapshot was not produced by cf-snapshot.js"
    try:
        gen = dt.datetime.fromisoformat(snap["generated_at"].replace("Z", "+00:00"))
    except Exception:
        return None, "snapshot has no generated_at"
    age = (dt.datetime.now(dt.timezone.utc) - gen).total_seconds() / 60
    if age > max_age_min:
        return None, f"snapshot is {age:.0f} min old (max {max_age_min}); take a fresh one"
    if age < -5:
        return None, "snapshot generated_at is in the future"
    snap["_age_min"] = round(age, 1)
    return snap, None

def doh(name, rtype):
    d = get_json(f"https://cloudflare-dns.com/dns-query?name={name}&type={rtype}", accept="application/dns-json")
    if d.get("Status") not in (0, 3):
        raise RuntimeError(f"DoH {name} {rtype} status {d.get('Status')}")
    tnum = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28, "DS": 43, "CAA": 257, "DNSKEY": 48}[rtype]
    return sorted(a["data"] for a in d.get("Answer", []) if a.get("type") == tnum)

def tls_accepts(version_flag):
    try:
        r = subprocess.run(["openssl", "s_client", version_flag, "-connect", f"{DOMAIN}:443", "-servername", DOMAIN],
                           input=b"", capture_output=True, timeout=20)
    except Exception as e:
        raise RuntimeError(f"openssl {version_flag}: {e}")
    out = (r.stdout + r.stderr).decode(errors="replace")
    if re.search(r"Protocol\s*:\s*TLSv|New, TLSv", out) and "Cipher is (NONE)" not in out and "Cipher    : 0000" not in out:
        return True
    return False

def collect_public_dns():
    names = {DOMAIN: ["NS", "CAA", "DS", "DNSKEY", "MX", "TXT"], f"_dmarc.{DOMAIN}": ["TXT"]}
    for sub in ["cpanel", "webdisk", "ftp", "autoconfig", "autodiscover", "mail"]:
        names[f"{sub}.{DOMAIN}"] = ["A", "CNAME"]
    out = {}
    for n, types in names.items():
        for t in types:
            out[f"{n} {t}"] = doh(n, t)
    tls = {}
    for flag, label in [("-tls1", "TLS1.0"), ("-tls1_1", "TLS1.1"), ("-tls1_2", "TLS1.2"), ("-tls1_3", "TLS1.3")]:
        tls[label] = tls_accepts(flag)
    out["tls_versions_accepted"] = tls
    st, body = None, None
    req = urllib.request.Request(f"https://{DOMAIN}/", method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        out["hsts_header"] = r.headers.get("strict-transport-security")
    return out

def collect_rdap():
    d = get_json(f"https://rdap.verisign.com/com/v1/domain/{DOMAIN}", tries=3)
    ev = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
    reg = None
    for e in d.get("entities", []):
        if "registrar" in (e.get("roles") or []):
            try:
                reg = [x[3] for x in e["vcardArray"][1] if x[0] == "fn"][0]
            except Exception:
                reg = e.get("handle")
    return {
        "registrar": reg,
        "status": sorted(d.get("status", [])),
        "nameservers": sorted(n.get("ldhName", "").lower() for n in d.get("nameservers", [])),
        "expiration": ev.get("expiration"),
        "last_changed": ev.get("last changed"),
        "secure_dns_delegation_signed": (d.get("secureDNS") or {}).get("delegationSigned"),
    }

def ca_of(issuer):
    m = re.search(r"O=([^,]+)", issuer or "")
    s = (m.group(1) if m else issuer or "?").strip().strip('"')
    return s

def collect_certs():
    """Union of crt.sh and Cert Spotter (crt.sh often lags or 502s). Returns (dict key->cert, source note).
    Keys are source-independent: not_before (to the minute) | issuer O= | sorted SANs."""
    certs, errs, used = {}, [], []
    def add(nb, na, ca, names, src):
        key = f"{nb}|{ca}|{','.join(names)}"
        c = certs.setdefault(key, {"not_before": nb, "not_after": na, "ca": ca, "names": names, "sources": []})
        if src not in c["sources"]:
            c["sources"].append(src)
    try:
        d = get_json(f"https://crt.sh/?q={DOMAIN}&output=json", tries=3, timeout=45)
        for c in d:
            add((c.get("not_before") or "")[:16], (c.get("not_after") or "")[:16], ca_of(c.get("issuer_name")),
                sorted(set(c.get("name_value", "").lower().split())), "crt.sh")
        used.append("crt.sh")
    except Exception as e:
        errs.append(f"crt.sh: {e}")
    try:
        d = get_json(f"https://api.certspotter.com/v1/issuances?domain={DOMAIN}&include_subdomains=true&expand=dns_names&expand=issuer", tries=2)
        for c in d:
            iss = c.get("issuer") or {}
            add((c.get("not_before") or "")[:16], (c.get("not_after") or "")[:16],
                ca_of(iss.get("name")) if iss.get("name") else iss.get("friendly_name", "?"),
                sorted(set(n.lower() for n in c.get("dns_names", []))), "certspotter")
        used.append("certspotter")
    except Exception as e:
        errs.append(f"certspotter: {e}")
    if not used:
        raise RuntimeError("; ".join(errs))
    return certs, " + ".join(used) + (f" (unavailable: {'; '.join(errs)[:120]})" if errs else "")

def known_deploy_ids():
    ids = set()
    for p in [ROOT / "seo" / "changes.csv", ROOT / "deploy_known_good" / "README.txt", ROOT / "deploy_known_good" / "deployment_id.txt"]:
        if p.is_file():
            t = p.read_text(errors="replace").lower()
            ids |= set(re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", t))
            ids |= set(re.findall(r"(?<![0-9a-z-])[0-9a-f]{8}(?![0-9a-z])", t))
    return ids

def dns_summary(bpath, cur):
    """Human list of added/removed DNS records versus baseline."""
    try:
        old = json.loads(bpath.read_text())
    except Exception:
        return "no baseline"
    key = lambda r: f"{r.get('type')} {r.get('name')} -> {r.get('content') or r.get('data')}" + (" (proxied)" if r.get("proxied") else "")
    o, n = {key(r) for r in old}, {key(r) for r in cur}
    parts = [f"added: {x}" for x in sorted(n - o)] + [f"removed: {x}" for x in sorted(o - n)]
    if not parts:
        parts = ["same records, changed TTL/priority/fields"]
    return "; ".join(parts)[:600]

DNSSEC_PENDING_MAX_DAYS = 7

def dnssec_check(cur, baselines, r):
    """Tracks DNSSEC 'pending' (DS not yet at the registrar). Flags pending > 7 days and any status move."""
    st = (cur or {}).get("status")
    since_p = baselines / "dnssec-pending-since.txt"   # state, not a baseline; written only while pending
    if st == "pending":
        if not since_p.is_file():
            since_p.write_text(dt.datetime.now(dt.timezone.utc).isoformat() + "\n")
        since = dt.datetime.fromisoformat(since_p.read_text().strip())
        days = (dt.datetime.now(dt.timezone.utc) - since).total_seconds() / 86400
        if days > DNSSEC_PENDING_MAX_DAYS:
            r.set("PROBLEM", f"DNSSEC still PENDING after {days:.0f} days (since {fmt_nz(since)}): add the DS record at Namecheap")
        else:
            r.lines.append(f"DNSSEC pending (DS record not yet at Namecheap) for {days:.1f} days; flagged if still pending after {DNSSEC_PENDING_MAX_DAYS} days")
    else:
        if since_p.is_file() and st == "active":
            r.set("CHANGED", "DNSSEC moved from pending to ACTIVE (DS record is live). Accept with: daily-watch.sh accept --reason '...' dnssec public_dns rdap")
            since_p.rename(since_p.with_suffix(".done"))
        elif st == "active":
            r.lines.append("DNSSEC active")
        else:
            r.set("PROBLEM" if st in ("disabled", "pending-disabled") and since_p.with_suffix(".done").is_file() else "INFO", f"DNSSEC status: {st}")

# ---------------------------------------------------------------- run
class Result:
    def __init__(self, section):
        self.section, self.status, self.lines, self.diff = section, "OK", [], ""
    def set(self, status, line=None):
        order = {"OK": 0, "INFO": 0, "UNCHECKED": 1, "CHANGED": 2, "PROBLEM": 2}
        if order[status] >= order.get(self.status, 0):
            self.status = status
        if line:
            self.lines.append(line)

def section_errors(snap, sec):
    keys = {sec}
    if sec == "worker":
        keys.add("worker_content")
    if sec == "zone_settings":
        keys.add("universal_ssl")
    if sec == "account":
        keys.add("user")
    if sec == "deployments":
        keys.update({"deployments_p1", "deployments_p2"})
    return [e for e in (snap.get("errors") or []) if e.split(":", 1)[0] in keys]


def auth_error(err):
    return bool(re.search(r"HTTP (401|403)\b", err or ""))


def compare(sec, current, baselines, res, ignore_missing=False, drop_unreadable=False):
    bpath = baselines / f"{sec}.json"
    if drop_unreadable and isinstance(current, list):
        current = [x for x in current if not (isinstance(x, dict) and x.get("rules_unreadable"))]
    (STATE / f"{sec}.json").write_text(canon(current))
    if not bpath.is_file():
        res.set("UNCHECKED", "no baseline yet; run: daily-watch.sh accept --reason '...' " + sec)
        return
    old_obj = json.loads(bpath.read_text())
    if drop_unreadable and isinstance(old_obj, list):
        old_obj = [x for x in old_obj if not (isinstance(x, dict) and x.get("rules_unreadable"))]
    if ignore_missing and isinstance(old_obj, dict) and isinstance(current, dict):
        lost = sorted(k for k in old_obj if k not in current)
        for k in lost:
            old_obj.pop(k)
        if lost:
            res.lines.append("not compared (token cannot read): " + ", ".join(lost))
    old = canon(old_obj)
    new = canon(current)
    if old == new:
        return
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "baseline", "now", n=1, lineterm=""))
    res.diff = "\n".join(d[:80]) + ("\n  ... (diff truncated)" if len(d) > 80 else "")
    added = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
    res.set("CHANGED", f"differs from baseline (+{added}/-{removed} lines)")

def set_state_dir(baselines):
    """Observed-state dir; separate per baselines dir so test runs can never feed a real `accept`."""
    global STATE
    if baselines.resolve() != DEFAULT_BASELINES.resolve():
        STATE = baselines / "_state"

def run(args):
    baselines = Path(args.baselines)
    set_state_dir(baselines)
    baselines.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results = []
    meta = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(), "baselines": str(baselines)}

    # (1) live integrity
    li = Result("live_integrity")
    if args.skip_live:
        li.set("UNCHECKED", "skipped (--skip-live)")
    else:
        try:
            p = subprocess.run(["bash", str(HERE / "live-integrity.sh")], capture_output=True, text=True, timeout=900)
            tail = [l for l in (p.stdout + p.stderr).strip().splitlines() if l.strip()][-4:]
            if p.returncode == 0:
                li.lines.append("live site byte-identical to deploy_known_good: " + (tail[-1][:160] if tail else "PASS"))
            elif p.returncode == 1:
                li.set("PROBLEM", "LIVE SITE DIFFERS FROM WHAT WE DEPLOYED (see scripts/security/reports/live-integrity-latest.txt)")
                li.lines += ["  " + t[:200] for t in tail]
            else:
                li.set("UNCHECKED", f"live-integrity could not reach the site (exit {p.returncode})")
        except Exception as e:
            li.set("UNCHECKED", f"live-integrity failed to run: {e}")
    results.append(li)

    # (3) Cloudflare snapshot sections
    snap, prob = load_cf_snapshot(args.cf_snapshot, args.max_snapshot_age)
    if snap:
        meta["cf_snapshot"] = {"generated_at": snap["generated_at"], "age_min": snap["_age_min"], "errors": snap.get("errors", [])}
    for sec in CF_SECTIONS:
        r = Result(sec)
        errs = section_errors(snap, sec) if snap else []
        if not snap:
            r.set("UNCHECKED", prob)
        elif sec not in snap.get("sections", {}):
            if errs and all(auth_error(e) for e in errs):
                # The token's policy does not include this section. Say so; do not fail the run.
                r.set("INFO", "not checked (token cannot read: " + errs[0] + ")")
            else:
                r.set("UNCHECKED", "not in snapshot" + (f" ({errs[0]})" if errs else ""))
        else:
            cur = snap["sections"][sec]
            partial = [e for e in errs if auth_error(e)]
            if sec == "rulesets":
                n_unread = sum(1 for x in cur if isinstance(x, dict) and x.get("rules_unreadable"))
                if n_unread:
                    r.lines.append(f"{n_unread} ruleset(s) not compared (token cannot read them)")
            compare(sec, cur, baselines, r,
                    ignore_missing=bool(partial) and sec in ("zone_settings", "account"),
                    drop_unreadable=sec == "rulesets")
            # standing hard checks (independent of baseline)
            if sec == "zone_settings":
                if cur.get("ssl") not in ("full", "strict"):
                    r.set("PROBLEM", f"SSL mode is {cur.get('ssl')!r} (expected full or strict)")
                sth = (cur.get("security_header") or {}).get("strict_transport_security") or {}
                if sth and not sth.get("enabled"):
                    r.set("PROBLEM", "HSTS disabled in zone settings")
            if sec == "dnssec":
                dnssec_check(cur, baselines, r)
            if sec == "dns" and r.status == "CHANGED":
                r.lines.insert(0, "DNS RECORDS CHANGED (Cloudflare has no DNS-change alert; this diff is the only DNS alarm): " + dns_summary(baselines / "dns.json", cur))
            if sec == "members" and len(cur) != 1:
                r.set("CHANGED", f"{len(cur)} account members (expected 1)")
            if sec == "zone" and cur.get("paused"):
                r.set("PROBLEM", "zone is PAUSED (Cloudflare bypassed)")
        results.append(r)

    # (2) deployments
    r = Result("deployments")
    raw_deps = snap.get("deployments") if snap else None
    if not snap or not isinstance(raw_deps, list) or not raw_deps:
        r.set("UNCHECKED", prob or "no deployments in snapshot (Pages token scope missing?)")
    else:
        known = known_deploy_ids()
        seen_p = baselines / "deployments.json"
        seen = json.loads(seen_p.read_text()) if seen_p.is_file() else None
        # Skip anything that is not a deploy object (e.g. the MCP's '--- TRUNCATED --- N more items' string).
        deps = [d for d in raw_deps if isinstance(d, dict) and isinstance(d.get("id"), str) and d.get("id")]
        skipped = len(raw_deps) - len(deps)
        if skipped:
            r.lines.append(f"skipped {skipped} non-deploy item(s) in the deployments list (e.g. a truncation note); not checked")
        cur_state = {"watch_since": (seen or {}).get("watch_since"), "accepted": (seen or {}).get("accepted", {}), "observed": [d["id"] for d in deps]}
        unknown = []
        for d in deps:
            did = d["id"].lower()
            if did in known or did[:8] in known or did in cur_state["accepted"]:
                continue
            if seen and seen.get("watch_since") and (d.get("created_on") or "") < seen["watch_since"]:
                continue  # predates the watch
            if not seen:
                continue
            unknown.append(d)
        (STATE / "deployments.json").write_text(canon({**cur_state, "unknown": [d["id"] for d in unknown]}))
        if not seen:
            r.set("UNCHECKED", "no deployments baseline yet; run accept")
        for d in unknown:
            try:
                when = fmt_nz(dt.datetime.fromisoformat(str(d.get("created_on")).replace("Z", "+00:00")))
            except Exception:
                when = "unknown time"
            r.set("PROBLEM", f"UNEXPECTED DEPLOY {d['id'][:8]} ({d.get('environment')}, {when}, {d.get('status')}, msg {str(d.get('message') or '')[:60]!r}): not in seo/changes.csv or deploy_known_good")
        live = (snap.get("canonical_deployment") or "").lower()
        kg_p = ROOT / "deploy_known_good" / "deployment_id.txt"
        kg = kg_p.read_text().strip().lower() if kg_p.is_file() else ""
        if live and kg and live != kg:
            r.set("PROBLEM", f"live production deployment is {live[:8]} but deploy_known_good says {kg[:8]}")
        elif live:
            r.lines.append(f"live production = {live[:8]} = deploy_known_good; {len(deps)} recent deployments checked, {len(unknown)} unexpected" + (f", {skipped} non-deploy item(s) skipped" if skipped else ""))
    results.append(r)

    # public DNS / TLS
    r = Result("public_dns")
    try:
        cur = collect_public_dns()
        compare("public_dns", cur, baselines, r)
        if cur["tls_versions_accepted"].get("TLS1.2") is False and cur["tls_versions_accepted"].get("TLS1.3") is False:
            r.set("PROBLEM", "site accepted neither TLS 1.2 nor 1.3 from this box")
    except Exception as e:
        r.set("UNCHECKED", f"public DNS/TLS lookups failed: {e}")
    results.append(r)

    # (5) RDAP
    r = Result("rdap")
    try:
        cur = collect_rdap()
        compare("rdap", cur, baselines, r)
        if "client transfer prohibited" not in cur["status"]:
            r.set("PROBLEM", "REGISTRAR TRANSFER LOCK IS OFF (no 'client transfer prohibited')")
        exp = dt.datetime.fromisoformat(cur["expiration"].replace("Z", "+00:00"))
        days = (exp - dt.datetime.now(dt.timezone.utc)).days
        if days < 30:
            r.set("PROBLEM", f"domain expires in {days} days ({fmt_nz(exp)})")
        elif days < 60:
            r.set("CHANGED", f"domain expires in {days} days; renew soon")
        else:
            r.lines.append(f"transfer lock on; expires {exp.date()} ({days} days); registrar {cur['registrar']}")
    except Exception as e:
        r.set("UNCHECKED", f"RDAP lookup failed: {e}")
    results.append(r)

    # (4) Certificate Transparency
    r = Result("certs")
    try:
        certs, source = collect_certs()
        bpath = baselines / "certs.json"
        base = json.loads(bpath.read_text()) if bpath.is_file() else None
        approved = []
        ap = baselines / "approved-cas.txt"
        if ap.is_file():
            approved = [l.split("#")[0].strip().lower() for l in ap.read_text().splitlines() if l.split("#")[0].strip()]
        state = {"seen": sorted(set(certs) | set((base or {}).get("seen", [])))}
        (STATE / "certs.json").write_text(canon(state))
        if base is None:
            r.set("UNCHECKED", f"no certs baseline yet ({len(certs)} certs seen via {source}); run accept")
        else:
            new = [certs[k] for k in sorted(certs) if k not in set(base.get("seen", []))]
            unapproved = [c for c in new if not any(a in c["ca"].lower() for a in approved)]
            ok_new = [c for c in new if c not in unapproved]
            for c in unapproved:
                r.set("PROBLEM", f"NEW CERTIFICATE from non-approved CA {c['ca']!r} for {','.join(c['names'])} (not before {c['not_before']} UTC)")
            for c in ok_new:
                r.lines.append(f"new certificate (approved CA {c['ca']}) for {','.join(c['names'])}, not before {c['not_before']} UTC; recorded automatically")
            if ok_new and not unapproved:
                bpath.write_text(canon({"seen": sorted(set(base.get("seen", [])) | {k for k, c in certs.items() if c in ok_new})}))
            r.lines.append(f"{len(certs)} certificates in CT via {source}; {len(new)} new since last run")
    except Exception as e:
        r.set("UNCHECKED", f"CT lookup failed: {e}")
    results.append(r)

    # ---------------------------------------------------------------- report
    meta["elapsed_s"] = round(time.time() - started, 1)
    (STATE / "_meta.json").write_text(canon(meta))
    bad = [x for x in results if x.status in ("CHANGED", "PROBLEM")]
    unk = [x for x in results if x.status == "UNCHECKED"]
    rc = 1 if bad else (2 if unk else 0)
    label = lambda s: LABELS.get(s, "Live site vs deployed files" if s == "live_integrity" else s)
    lines = []
    head = {0: "ALL CLEAR", 1: "CHANGE OR PROBLEM FOUND", 2: "COULD NOT CHECK EVERYTHING"}[rc]
    lines.append(f"trendibizz.com daily watch, {fmt_nz(now_nz())}: {head} (exit {rc})")
    lines.append("")
    if rc == 0:
        lines.append(f"Everything matched: the live site, Cloudflare settings, DNS, deploys, registrar lock and certificates ({len(results)} checks).")
    if bad:
        lines.append("Needs a look:")
        for x in bad:
            lines.append(f"  - {label(x.section)}: " + "; ".join(l for l in x.lines if l)[:300])
        lines.append("If this was an approved change (e.g. Omega Boss's DNSSEC/CAA/DNS/notification work), re-baseline with:")
        lines.append("  bash scripts/security/daily-watch.sh accept --reason 'who: what' " + " ".join(x.section for x in bad if x.section not in ("live_integrity",)))
        lines.append("If it was NOT approved: treat as possible tampering (see README 'On a FAIL').")
    if unk:
        lines.append("Could not check:")
        for x in unk:
            lines.append(f"  - {label(x.section)}: " + "; ".join(x.lines)[:300])
    lines.append("")
    lines.append(f"Runtime {meta['elapsed_s']} s. Cloudflare snapshot: " + (f"{snap['generated_at']} ({snap['_age_min']} min old)" if snap else "none"))
    lines.append("=" * 72)
    for x in results:
        lines.append(f"[{x.status:9}] {label(x.section)}")
        for l in x.lines:
            lines.append(f"            {l}")
        if x.diff:
            lines.append("            diff:")
            lines += ["              " + l for l in x.diff.splitlines()]
    report = "\n".join(lines) + "\n"
    stamp = now_nz().strftime("%Y%m%d-%H%M%S")
    (REPORTS / "daily-watch-latest.txt").write_text(report)
    (REPORTS / f"daily-watch-{stamp}.txt").write_text(report)
    for old in sorted(REPORTS.glob("daily-watch-2*.txt"))[:-60]:   # keep the last 60 dated reports
        old.unlink()
    print(report, end="")
    return rc

# ---------------------------------------------------------------- accept
def accept(args):
    baselines = Path(args.baselines)
    set_state_dir(baselines)
    baselines.mkdir(parents=True, exist_ok=True)
    meta_p = STATE / "_meta.json"
    if not meta_p.is_file():
        print("accept: no observed state; run daily-watch.sh first", file=sys.stderr); return 2
    meta = json.loads(meta_p.read_text())
    age_h = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(meta["run_at"])).total_seconds() / 3600
    if age_h > 24:
        print(f"accept: last run is {age_h:.1f} h old; run daily-watch.sh again first", file=sys.stderr); return 2
    if Path(meta.get("baselines", "")).resolve() != baselines.resolve():
        print("accept: the last observed state belongs to a different baselines dir; run daily-watch.sh first", file=sys.stderr); return 2
    if not args.reason or len(args.reason.strip()) < 8:
        print("accept: --reason 'who approved: what changed' is required", file=sys.stderr); return 2
    secs = args.sections or ["all"]
    if "all" in secs:
        secs = ALL_SECTIONS
    bad = [s for s in secs if s not in ALL_SECTIONS]
    if bad:
        print(f"accept: unknown section(s) {bad}; valid: {' '.join(ALL_SECTIONS)} all", file=sys.stderr); return 2
    hist = baselines / "history" / now_nz().strftime("%Y%m%d-%H%M%S")
    done = []
    for s in secs:
        src = STATE / f"{s}.json"
        if not src.is_file():
            continue
        dst = baselines / f"{s}.json"
        if dst.is_file():
            hist.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, hist / dst.name)
        if s == "deployments":
            cur = json.loads(src.read_text())
            old = json.loads(dst.read_text()) if dst.is_file() else {}
            acc = dict(old.get("accepted", {}))
            for did in cur.get("unknown", []):
                acc[did] = args.reason
            new = {"watch_since": old.get("watch_since") or meta["run_at"], "accepted": acc}
            dst.write_text(canon(new))
        else:
            shutil.copy2(src, dst)
        done.append(s)
    with open(baselines / "ACCEPT-LOG.txt", "a") as f:
        f.write(f"{fmt_nz(now_nz())}\t{','.join(done)}\trun {meta['run_at']}\t{args.reason.strip()}\n")
    print(f"accepted {len(done)} section(s) from the run at {fmt_nz(dt.datetime.fromisoformat(meta['run_at']))}: {' '.join(done)}")
    if hist.exists():
        print(f"previous baselines saved in {hist}")
    return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="run", choices=["run", "accept"])
    ap.add_argument("sections", nargs="*", help="accept: sections to re-baseline (default all)")
    ap.add_argument("--cf-snapshot", default=os.environ.get("DAILY_WATCH_CF_SNAPSHOT"))
    ap.add_argument("--baselines", default=os.environ.get("DAILY_WATCH_BASELINES", str(DEFAULT_BASELINES)))
    ap.add_argument("--max-snapshot-age", type=int, default=120, help="minutes")
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--reason")
    a = ap.parse_args()
    if a.mode == "accept":
        sys.exit(accept(a))
    try:
        sys.exit(run(a))
    except Exception as e:
        print(f"daily-watch: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
