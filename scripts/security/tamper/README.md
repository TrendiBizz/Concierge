# trendibizz.com tamper watch

Read-only daily check: is the live site what the repo says we deployed, and did
anything in Cloudflare, DNS, the registrar or the certificate logs change?

Moved into the central repo on 2026-11-17 from
`~/OpenBot/Shared/workwatch/tamper-watch/security/`. The central repo's
`website/` tree is now the known-good, replacing the stale
`trendi-site/deploy_known_good` snapshot (3 Nov) that made every run report a
site "tamper" after the Concierge cutover.

| File | Purpose |
|---|---|
| `daily-watch.sh` | Lock + entry point for a run |
| `daily_watch.py` | Compares Cloudflare snapshot, live site, public DNS, RDAP, CT |
| `live-integrity.sh` / `live_integrity.py` | Fetches the live site and compares it byte-for-byte with `website/` |
| `cf-snapshot.js` | GET-only Cloudflare snapshot (DNS, DNSSEC, zone, settings, rulesets, Workers, members, notifications, Page Shield, Pages) |
| `cf-run-snapshot.js` / `run-snapshot.sh` | Mac runner: reads the token from the Keychain into the process env |
| `baselines/` | Accepted state, one JSON per section, plus `ACCEPT-LOG.txt` |
| `reports/` | Run output (gitignored) |
| `tests/` | Regression tests (`python3 -m unittest discover -s tests`, `node tests/test_snapshot.js`) |

## How the token is read

`run-snapshot.sh` is the **only** place a token enters the process:

```
security find-generic-password -s trendi-cf-readonly-token -w
  -> CF_READONLY_TOKEN=<env, this process only>
  -> cf-run-snapshot.js (GET-only fetch, never prints or writes the token)
```

`~/.config/trendi/cloudflare_token` is a **copy**, not the watch's input. If it
and the Keychain differ, the Keychain wins. To rotate: update the Keychain item
`trendi-cf-readonly-token` first, then the file, then re-run the scope probe.

## Token scopes (read-only)

Required for a complete run:

- Zone: DNS, Zone, Zone Settings, SSL and Certificates, Firewall Services, Workers Routes
- Account: Pages, Workers Scripts, Account Settings, Notifications
- User: User Details (for the `/user` 2FA check)

As of 2026-11-17 the Mac token has all of these **except Pages Read** (and the
`user`/Universal SSL sub-reads), so the Pages project and deployment check is
honestly reported as "could not check". See `QA/verification/TAMPER_WATCH_2026-11-17.md`.

## Run

```bash
cd /Users/jo/work-staging/concierge-integration
bash scripts/security/tamper/run-snapshot.sh /tmp/cf.json
bash scripts/security/tamper/daily-watch.sh --cf-snapshot /tmp/cf.json
```

Exit: `0` all clear · `1` change/problem · `2` something could not be checked
(and nothing changed). A 403 section is reported as **INFO "not checked (token
cannot read)"**, never as a change; an empty Pages deployment list is
**UNCHECKED**, never OK.

## Baselines

Only accept a flag after checking it against the change ledger
(`docs/`, `QA/verification/`, the jo-brain handover, the Cloudflare change log):

```bash
bash scripts/security/tamper/daily-watch.sh accept --reason 'who: what, evidence' dns public_dns
```

Every accept appends to `baselines/ACCEPT-LOG.txt` and copies the previous
files into `baselines/history/<timestamp>/`. **Never accept the mail DNS or
DMARC items** without Jo's explicit confirmation.

## Cloudflare edge transforms that are not site changes

`live_integrity.py` strips only these exact, pinned shapes before hashing:

- the Cloudflare Web Analytics beacon (`cf-beacon.txt` pins the site token);
- the bot-management challenge loader injected into HTML;
- the literal `'nonce-{CSP_NONCE}'` source that bot management adds to CSP.

A different beacon token, a different CSP source, or a challenge **page** still
fails. `_headers` and `_redirects` are config files and are not fetched.

## Tests

```bash
cd scripts/security/tamper
python3 -m unittest discover -s tests -v     # daily_watch + live_integrity
/opt/homebrew/opt/node@24/bin/node tests/test_snapshot.js
```

Tests cover the 2026-11-17 defects: a hard-coded unscoped-section list, an
empty deployment list read as all-clear, false CHANGED on partially readable
sections, and Cloudflare's injected challenge/CSP nonce counted as tampering.
