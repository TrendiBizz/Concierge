# Trendi security checks (trendibizz.com)

Added 2026-11-02. Built for one job: stop anyone from slipping malicious
code into the site, or pointing us or our visitors at a harmful site.
Everything here is free, uses only the Python standard library, and needs
no accounts or API keys.

| Tool | When it runs | What it answers |
|---|---|---|
| `scripts/security-scan.py` | **Automatically on every deploy** (inside `preflight-manifest.sh`, which `deploy-production.sh` runs twice). You can also run it by hand on any stage. | "Is there anything in this site folder that shouldn't be there?" |
| `scripts/security/live-integrity.sh` | **Daily**, and after any deploy. | "Is the live site exactly what we deployed?" |
| `scripts/security/check-url.sh <url>` | Before a new link goes on the site, and before any bot follows a link from a brief, email or DM. | "Is this URL safe?" |
| `scripts/security/tests/run-tests.sh` | After editing the scanner. | Proves every rule still fires. |

---

## 1. The deploy gate: `security-scan.py`

```bash
python3 scripts/security-scan.py                       # scans site/ (exit 0 PASS, 1 FAIL, 2 error)
python3 scripts/security-scan.py --site staged/X/site  # scan a stage
python3 scripts/security-scan.py --inventory           # also list every outbound host
WORKER_SRC=staged/X/worker python3 scripts/security-scan.py   # also review a new _worker.js
SECURITY_SCAN_OFFLINE=1 ...                            # use cached threat feeds only (no downloads)
```

It runs in about 1 second and the feeds are cached for 12 hours. When a feed
can't be downloaded, the scan uses the cached copy for up to 7 days and
prints a WARN; it doesn't fail because of a feed outage.

**How it's wired in.** `scripts/preflight-manifest.sh` has a block just
before `=== PREFLIGHT SUMMARY ===`, marked
`# --- Security gate (added 2026-11-02 ...)`. A scan FAIL, or a missing
scanner, counts as a preflight FAIL, so `deploy-production.sh` refuses to
upload. There is deliberately no skip switch. The pre-change script is
backed up at `scripts/preflight-manifest.sh.bak-pre-security-20261102`.
To undo the wiring, delete that block or restore the backup.

### What it blocks (FAIL = deploy refused)

| Rule | Blocks |
|---|---|
| SEC-DOMAIN | Any outbound URL (link, JSON-LD, JS string, `_redirects` target) whose host isn't in `allowed-domains.txt`. It also catches open-redirect smuggling: an allowlisted host that carries another site in its query string, e.g. `?url=https://evil`. |
| SEC-NEWDOMAIN | A host that was never on the live site, unless its allowlist line says `approved-by:`. |
| SEC-HTTP | Any `http://` URL, except the XML namespace ids in `allowed-http-urls.txt`. |
| SEC-IPURL | URLs that point at a bare IP address. |
| SEC-EXTSCRIPT | External `<script src>`, stylesheets, fonts, preloads, modules and imports, unless the host is in `allowed-embeds.txt` (empty today). |
| SEC-IFRAME | Any `<iframe>`, `<frame>`, `<object>`, `<embed>` or `<applet>`; hidden ones are labelled HIDDEN. |
| SEC-FORM | A `<form action>` that posts to another site. |
| SEC-INLINE | An executable inline `<script>` whose CSP-style sha256 isn't in `allowed-inline-script-hashes.txt` (empty today). JSON-LD is data: it's exempt from hashing, but it must parse as JSON, and its URLs go through the domain rules. |
| SEC-HANDLER | Inline event handlers (`onclick=`, `onerror=` …). |
| SEC-JSURL | `javascript:`, `vbscript:` and `data:text/html` URLs. |
| SEC-REFRESH | `<meta http-equiv=refresh>` to another site, or an external `<base href>`. |
| SEC-OBFUSC | Base64 blobs of 200+ characters, `eval(`, `new Function(`, `atob(`, `String.fromCharCode`, `unescape(`, `document.write(`, string timers, runs of `\x`/`\u` escapes, `_0x` names, JSFuck, dynamic `<script>`/`<iframe>` creation, raw HTML sinks, `import()` from a URL, WebSocket/EventSource, `sendBeacon`, and CSS `expression()`. |
| SEC-HIDDENLINK | External links inside inline-hidden elements (SEO-spam injection). |
| SEC-BADMARKER | Crypto-miner names, card-skimmer fields (`cc-number`, `cvv` … card data belongs only on Stripe), pharma/casino/adult spam words, and web-shell or defacement strings. |
| SEC-CSP | A CSP that's missing, has a directive removed, or adds any source or keyword compared with the live baseline (dangerous tokens such as `'unsafe-eval'`, `*` and `data:` are called out). Tightening the CSP is always allowed. |
| SEC-HEADER | HSTS, nosniff, X-Frame-Options, Referrer-Policy, Permissions-Policy or COOP/CORP removed or changed, compared with live. |
| SEC-REDIRECT | `_redirects` rules that send visitors to a non-allowlisted or `http://` site. |
| SEC-FILETYPE | Extensions outside the allowed set, server-side code, executables and archives (`.php`, `.exe`, `.zip` …), dotfiles (`.env`, `.git`) and symlinks. |
| SEC-MAGIC | A file whose bytes don't match its extension (e.g. an EXE renamed to `.png`). |
| SEC-SVG | Script, event handlers or `foreignObject` inside an SVG. |
| SEC-CSV | Spreadsheet formula injection (`=`, `+`, `-`, `@` at the start of a cell) in downloadable CSVs. |
| SEC-THREAT | A host or URL on a free threat feed (URLhaus mirror, phishing feeds, Phishing.Database, OpenPhish) or on `local-blocklist.txt`. |
| SEC-WORKER | WARN when `_worker.js` (from `$WORKER_SRC` or deploy_known_good) differs from live; review the diff. FAIL if the new worker gains obfuscation or markers, a new host, or an `http://` URL. |

WARN lines never block a deploy. Current WARNs:
- placeholder hosts such as `your-domain` (no dot) in example text;
- a changed worker.

### Approving something new (requires a human)

Every decision is a one-line edit with a who/when/why comment, so changes
show up in diffs.

- **New outbound domain.**
  1. Run `bash scripts/security/check-url.sh https://the.new/page`. It must print PASS, or REVIEW with an explained reason.
  2. Get Jo's OK (or Omega Boss's under Jo's delegation).
  3. Add `the.new  # approved-by: Jo 2026-11-03 partner page link (check-url PASS)` to `allowed-domains.txt`.

  Subdomains are not implied, so `www.` and the bare domain need separate lines. `www.google.com` is left out on purpose (its `/url?q=` open redirect is a phishing favourite). If the Maps link ever comes back, add it with `approved-by:`.
- **Third-party script, iframe, font or form target.** Add the host to `allowed-embeds.txt` **and** make the matching CSP change. The CSP change also fails until its sha256 (printed in the failure) is added to `csp-approved.txt`. Both lines need `approved-by:`.
- **Inline script.** Prefer a self-hosted `.js` file; the CSP blocks inline code anyway. If one is truly needed, add the `sha256-…` printed by the scan to `allowed-inline-script-hashes.txt`, and to the CSP.
- **Feed false positive on a big legitimate host.** Add `threat-exempt: <reason>` to that host's allowlist comment. SEC-THREAT then becomes a WARN for feed hits; hits on `local-blocklist.txt` are never exempt.
- **Known-bad host** that someone tried to point us at: add it to `local-blocklist.txt`. Parent domains match too.

### Domains outside site/

The gate scans every file in the deploy tree:
- `.html`, `.js`, `.css`, `.txt`, `.xml`, `.json`, `.svg` and `.md` files;
- `_headers` and `_redirects`;
- `/research/*.csv`, but only for markers and formula injection, because it is a dataset of 100 company domains rather than links.

---

## 2. Daily live tamper check: `live-integrity.sh`

```bash
bash /workspace/trendi/scripts/security/live-integrity.sh
```

It downloads every path in `deploy_known_good/manifest.json` from
https://trendibizz.com without following redirects:
- about 61 GETs and 13 MB;
- about 3 seconds;
- no key needed.

It then checks:
- **Content.** Every file must be byte-identical (sha256) to what we deployed. A mismatch report lists the new hosts, new `<script>` tags and a short diff.
- **Headers.** The CSP must match exactly; HSTS, nosniff, XFO, Referrer, Permissions, COOP, CORP, X-Robots-Tag and Content-Type are checked per `headers.txt`.
- **Statuses and redirects.**

  | Probe | Expected |
  |---|---|
  | `www` | 301 to apex |
  | `/shop`, `/wp-login.php` | 410 |
  | `/tools/security-check` | 301 to `/security-check` |
  | `/_headers`, `/_redirects`, `/_worker.js`, `/.git/config` | 404 |
  | random path | 404 |

  Any redirect to another site is a FAIL. `http://` to `https://` is checked where port 80 is reachable; this box can't reach port 80, so that probe is skipped here.
- **Cloudflare Web Analytics.** Cloudflare injects one beacon `<script>` into HTML served to browsers. Only that exact tag shape from `static.cloudflareinsights.com`, carrying our token in `cf-beacon.txt`, is ignored. A different token or a lookalike host fails.

Exit codes:
- 0 PASS;
- 1 FAIL, with a report in `scripts/security/reports/live-integrity-<time>.txt` and `live-integrity-latest.txt`;
- 2 site unreachable.

If `deploy_known_good` changed less than 30 minutes ago, a FAIL is re-checked once after 6 minutes, because edge caches such as `max-age=300` on JS and CSS need time to turn over. Set `LIVE_INTEGRITY_NO_RETRY=1` to skip the wait.

**On a FAIL with no deploy in progress:**
1. Treat it as possible tampering.
2. Roll back to the last known-good deployment ID (see `deploy_known_good/README.txt`).
3. Rotate the Cloudflare API token and Pages JWT.
4. Tell Jo.

If someone deployed without updating `deploy_known_good`, update it, then re-run.

---

## 3. URL checker: `check-url.sh`

```bash
bash scripts/security/check-url.sh https://some.site/page [more urls] [--json] [--no-fetch]
```

Exit codes: 0 PASS · 3 REVIEW (a human should look) · 1 FAIL (don't use or follow).

| Check | Result |
|---|---|
| Not `https://`; `user@host` disguise; bare IP; path ending in an executable or archive extension | FAIL |
| Punycode (`xn--`, possible lookalike); link shortener | REVIEW |
| On a threat list (same feeds as the gate, plus `local-blocklist.txt`) | FAIL |
| Doesn't resolve, checked via Cloudflare DNS-over-HTTPS so a local proxy can't hide a dead domain | FAIL (dead or expired, anyone can buy it) |
| Resolves to a private address | FAIL |
| Domain age via free RDAP: under 30 days | FAIL |
| Domain age via free RDAP: under 180 days | REVIEW |
| Registration expired | FAIL |
| Registration expires within 30 days | REVIEW |
| `.nz` domain (no public RDAP) | Age shows "unknown" as info |
| Redirects (followed by hand, up to 10 hops): any hop that downgrades to `http://` | FAIL |
| Redirects: hop to a different site | REVIEW |
| Redirects: target on a threat list | FAIL |
| Final URL serves an executable download | FAIL |
| Final URL returns 4xx/5xx | REVIEW (401/403/429/999 is noted as "blocks bots") |

**When to use it:**
- before adding any new link to the site, which is also step 1 of approving a new domain;
- before a bot or agent opens a URL that came from a brief, email, DM, form submission, partner or "check out this site" message;
- when a tool user reports a weird result for a URL;
- monthly, on every outbound URL, to catch link rot and expired domains. The list comes from `security-scan.py --json-out`; see the audit doc for the one-liner.

---

## 4. Daily tamper + unexpected-change watch: `daily-watch.sh`

**Read-only.** Every call it makes is a GET or a public lookup: the Cloudflare API via the MCP snapshot, DoH, RDAP, crt.sh/Cert Spotter, the live site, and openssl. It never changes Cloudflare, DNS, the registrar or the site. The only files it writes are its own baselines and reports.

### Run it (routine = two steps, in this order)

1. **Cloudflare snapshot**, through the Cloudflare MCP connector (the credential is the MCP OAuth login as kiwi18@gmail.com):
   `CallDynamicTool` namespace `user-Cloudflare`, tool `execute`, arguments
   `{"code": "$file:/workspace/trendi/scripts/security/cf-snapshot.js"}`, with `write_to_file: true`.
   The call writes the result to `/workspace/agent-tools/<id>.txt`. `cf-snapshot.js` only does GETs and collects no secret values: Pages env vars are recorded by name and type only.
2. **The watch:**
   ```
   bash /workspace/trendi/scripts/security/daily-watch.sh --cf-snapshot /workspace/agent-tools/<id>.txt
   ```
   The run takes about 16–40 s and is headless, with no prompts. It holds a lock in `/tmp/trendi-daily-watch.lock`, so two runs can't overlap.

**Why it doesn't use an API token:** there is no Cloudflare API token on the box, and listing or creating tokens through OAuth returns 403. The MCP OAuth session has **Super Admin** rights, but the snapshot code only reads.
- **Recommended upgrade:** Jo creates a custom token with read-only permissions (Zone: DNS/Zone/Zone Settings/Firewall/Workers Routes Read; Account: Pages/Workers Scripts/Account Settings/Notifications Read) and stores it outside the box's shared files.
- Until then, the run needs the snapshot. With `--cf-snapshot` missing, or a snapshot older than 120 min (`--max-snapshot-age`), the Cloudflare sections report UNCHECKED and the exit is 2.

### What it checks (each against a baseline in `baselines/`)

| Section | Flags |
|---|---|
| live_integrity | runs `live-integrity.sh`; anything except PASS |
| dns | any record added, removed or changed. **Cloudflare has no DNS-change notification, so this diff is the only DNS alarm.** |
| dnssec | any change. **Pending → active** is reported as CHANGED (good news: the DS record is live; accept it). Still pending **after 7 days** (counted from `baselines/dnssec-pending-since.txt`) is a PROBLEM. |
| zone, zone_settings | nameservers, plan, paused status; SSL mode (must be full or strict), min TLS, HSTS (must be on), Always-HTTPS, etc. |
| rulesets | WAF, redirect and cache rules (managed rulesets are tracked by identity) |
| worker_scripts, worker, worker_routes | new Workers; the `trendi-force-https` source sha256 (canonicalised multipart); routes |
| members, account | any new member or role change (exactly one member expected); 2FA enforcement |
| notifications, page_shield | alert policies removed or changed |
| pages_project | build config, env var names, custom domains |
| deployments | newest 50 deployments only (`cf-snapshot.js` caps it so the MCP output is never truncated; fix 2026-11-03). Any list item that is not a deploy object (e.g. a `--- TRUNCATED --- N more items` note) is skipped and counted in the report, never a crash. Flags any Pages deployment created after the watch started whose ID is not in `seo/changes.csv`, `deploy_known_good/README.txt`, `deployment_id.txt`, or the accepted list. Also flags when live production ≠ `deploy_known_good/deployment_id.txt`. |
| public_dns | public view via DoH: A/AAAA/NS/MX/TXT/CAA/DS/DMARC, plus a TLS-version probe |
| rdap | Verisign RDAP: transfer lock missing → PROBLEM; expiry under 60 days → CHANGED, under 30 days → PROBLEM |
| certs | crt.sh and Cert Spotter combined. A new certificate from a CA not in `baselines/approved-cas.txt` is a PROBLEM. New certificates from approved CAs are listed and recorded (normal Cloudflare renewals). |

**TLS probe caveat:** the box goes out through Cloudflare WARP, and its openssl can't do TLS 1.0/1.1, so the probe can't show legacy TLS. The authoritative signal is `zone_settings.min_tls_version`.

### Output and exit codes

- `reports/daily-watch-latest.txt` holds a plain-English summary at the top, then one line per section. A timestamped copy `reports/daily-watch-YYYYMMDD-HHMMSS.txt` is also written.
- **0** = all clear · **1** = something changed or a problem was found (read the summary) · **2** = something couldn't be checked (snapshot missing or stale, or a network failure).

### Accepting an approved change (re-baselining)

**The first runs after any approved change will flag it, by design.** Examples:
- Omega Boss's DS record at Namecheap: dnssec + public_dns change.
- A DMARC tightening: dns + public_dns.
- Raising min TLS: zone_settings.
- A new deploy through the gate: recorded in `seo/changes.csv`, so it is not flagged.

Once you've confirmed the change was approved:
```
bash scripts/security/daily-watch.sh accept --reason 'Omega Boss: DS added at Namecheap 2026-11-0X' dnssec public_dns
bash scripts/security/daily-watch.sh accept --reason 'Jo: DMARC p=quarantine' dns public_dns
bash scripts/security/daily-watch.sh accept --reason 'who: what' all
```
- `accept` copies the **last run's** observed state into `baselines/`. The last run must be under 24 h old and must have used the same baselines dir.
- The old baselines are saved in `baselines/history/<timestamp>/`, and each accept is logged in `baselines/ACCEPT-LOG.txt`.
- Accepting `deployments` adds the flagged deploy IDs to the accepted list.
- **Don't accept anything you can't explain.** An unexplained change is a possible tamper; see "On a FAIL" in section 2.

**Baseline history:**
- Initial baseline: 2026-11-02 16:03 NZDT, taken *after* Omega Boss's approved changes: 7 notification policies, DNSSEC enabled (pending DS, key tag 2371, alg 13), CAA records (letsencrypt.org, pki.goog, ssl.com, plus iodef), and 5 cPanel A records deleted. Log: `security/cf-changes-20261102.md`.
- **Expected next flag:** DNSSEC pending → active once the DS record is at Namecheap. Accept it with `accept --reason '...' dnssec public_dns`.

### Tests run on 2026-11-02 (on temporary copies of the baselines)

| Test | Result |
|---|---|
| Clean run | exit 0 |
| Simulated drift: DNS change, DNSSEC pending 8 days, Worker hash changed, rogue deploy `deadbeef` | exit 1, all four flagged |
| Stale snapshot | exit 2 |
| Certificate from a non-approved CA | exit 1 |
| DNSSEC pending → active | flagged; the accept hint shown; accept, then re-run clean |

2026-11-03 fix tests (temp baseline copies): synthetic snapshot with a truncation string, an id-less dict and an int in `deployments` → no crash, "skipped 3 non-deploy item(s)", exit 0 once the temp copy matched the live DNS; this morning's raw truncated snapshot → no crash, 1 skipped. Fresh capped snapshot: 50 deploys, 0 errors, no truncation.

Test runs use `--baselines /tmp/...` (or `DAILY_WATCH_BASELINES`), which keeps their observed state in `<baselines>/_state/`, so a test can never feed a real `accept`. They do still overwrite `reports/daily-watch-latest.txt`, so re-run the real watch after testing.

---

## Optional keys (all optional; nothing breaks without them)

| Key | Where | What it adds | Note |
|---|---|---|---|
| `URLHAUS_AUTH_KEY` | env or `~/.config/trendi/urlhaus_auth_key` | Live URLhaus host lookup (the no-key mirror list is already used) | Needs a free abuse.ch account (auth.abuse.ch) |
| `GOOGLE_SAFE_BROWSING_KEY` | env or `~/.config/trendi/gsb_api_key` | Google Safe Browsing v4 lookups | Free Google Cloud key, but its terms are **non-commercial**. Trendi is commercial, so Google points to Web Risk instead (it has a free monthly tier). Jo to decide. |

Never paste keys into chat or put them in the repo. Without keys, the tools print `INFO … skipped` and carry on.

## Files

```
scripts/security-scan.py                  gate (stdlib only)
scripts/security/threatlist.py            shared feed loader (.cache/, 12 h TTL)
scripts/security/allowed-domains.txt      outbound host allowlist (seeded from live 2026-11-02)
scripts/security/allowed-embeds.txt       third-party script/iframe/font hosts (empty)
scripts/security/allowed-inline-script-hashes.txt  (empty)
scripts/security/allowed-http-urls.txt    xmlns ids + OFL licence URL
scripts/security/csp-approved.txt         approved CSP loosenings (empty)
scripts/security/local-blocklist.txt      our own blocklist
scripts/security/cf-beacon.txt            our Cloudflare Web Analytics token
scripts/security/live-integrity.sh/.py    daily tamper check
scripts/security/check-url.sh / check_url.py
scripts/security/tests/run-tests.sh       poison tests for the gate (46 cases)
scripts/security/tests/test_live_integrity.py  tamper tests for the live check (8 cases)
scripts/security/reports/                 live-integrity + daily-watch reports (last 60 dated daily-watch reports kept)
scripts/security/daily-watch.sh / daily_watch.py   daily tamper + unexpected-change watch (read-only)
scripts/security/cf-snapshot.js           read-only Cloudflare snapshot (run via Cloudflare MCP execute)
scripts/security/baselines/               watch baselines, approved-cas.txt, ACCEPT-LOG.txt, history/
scripts/security/reports/daily-watch-state/  last run's observed state (what `accept` copies)
```
