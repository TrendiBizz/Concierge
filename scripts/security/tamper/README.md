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
| `deployments_ledger.csv` | Pages deployment ids approved before this repo held the watch (migrated from the old `seo/changes.csv`) |
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

As of 2026-11-17 20:41 the Mac token has Pages Read (Jo added it), so the Pages
project and deployment check run. It still lacks **Zone** SSL and Certificates Read
(the Account scope does not cover the zone endpoint), User Details Read, and the
redirect ruleset detail, so those are honestly reported as "could not check". See
`QA/verification/TAMPER_WATCH_2026-11-17.md`.

## Run

```bash
# Mac (Keychain token)
cd /Users/jo/work-staging/concierge-integration
bash scripts/security/tamper/run-snapshot.sh /tmp/cf.json
bash scripts/security/tamper/daily-watch.sh --cf-snapshot /tmp/cf.json

# Hermes container (mounted 0600 token copy, reports to the mounted dir)
docker exec hermes-concierge bash /opt/data/concierge/scripts/security/tamper/run-snapshot.sh /tmp/cf.json
docker exec hermes-concierge bash /opt/data/concierge/scripts/security/tamper/daily-watch.sh --cf-snapshot /tmp/cf.json
```

`start-master.sh` sets `TRENDI_SITE_ROOT=/opt/data/concierge` and
`TRENDI_TAMPER_REPORTS=/opt/data/.workwatch/reports/tamper` for the container.
Baselines are mounted read-only there, so `accept` is a Mac-side action.

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
files into `baselines/history/<timestamp>/`. Per-item **revert instructions** live in
`baselines/CHANGES.md`. **Never accept the mail DNS or DMARC items** without Jo's
explicit confirmation (given 2026-11-17). A section the token can only partially
read is accepted by keeping the old baseline for the unreadable key/ruleset.

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
