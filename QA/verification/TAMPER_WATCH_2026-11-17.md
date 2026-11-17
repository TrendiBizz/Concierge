# Tamper watch: token path, scope truth, stale known-good and four silent bugs

Date: 2026-11-17 (NZDT) · Repo: `/Users/jo/work-staging/concierge-integration` (main)
Work: HANDOFF.md M4 / `hermes/JOBS.md` T1 — get the daily tamper watch trustworthy
before resuming it.

## Result in one line

The live site is **not** being tampered with: it is byte-identical to `website/` at
repo `7c8b113` (107/107 files, 0 fails). Every previous "site differs" alarm came
from a known-good snapshot that stopped being updated on 3 Nov. The watch itself
had four defects that could hide a real change; all four are fixed and tested. Two
items still block resuming the cron job: the token cannot read Pages, and the mail
DNS/DMARC change is unconfirmed.

## 1. How the watch reads the token (verified)

```
run-snapshot.sh
  security find-generic-password -s trendi-cf-readonly-token -w
    -> CF_READONLY_TOKEN (env of this process only)
      -> cf-run-snapshot.js  (GET only; never prints or writes the token)
```

`~/.config/trendi/cloudflare_token` is **not** read by the watch. It is a copy.
On this machine both were the same token: SHA-256
`219e1e0284b61a81565fd3ecc0a74a45a4a504dfea9dde70a01a2b7a309c74a3` after trimming the
trailing newline the Keychain adds. No token value was printed.

## 2. Scope probe (live GETs, 2026-11-17 20:18 NZDT)

| Endpoint | Result |
|---|---|
| `/user/tokens/verify` | 200 active |
| DNS, zone, DNSSEC, zone settings, rulesets list, Worker scripts, Worker routes, account, notifications, Page Shield | 200 |
| `/zones/:id/ssl/universal/settings` | **403** — SSL and Certificates Read missing |
| `/user` | **403** — User Details Read missing |
| `/zones/:id/rulesets/:id` (`http_request_dynamic_redirect`) | **403** |
| `/accounts/:id/pages/projects/trendi` and deployments | **403 at 20:18** → **200 at 20:41** after Jo added Cloudflare Pages: Read |

Pages Read was the serious gap: without it the "unexpected deployment" check was
blind. Jo added **Account -> Cloudflare Pages: Read** at 20:41; the re-probe returned
200 and a fresh snapshot contains `pages_project` and 50 deployments. The Universal
SSL 403 persists because the added scope was *Account* SSL and Certificates; the
zone endpoint needs the **Zone** variant. `/user` and the redirect ruleset detail
remain 403.

Adding Pages exposed a second gap: the repo had no deployment ledger, so the six
Pages deploys between 2 and 8 Nov (all recorded in the old
`trendi-site/seo/changes.csv`) were reported as unexpected. They are now in
`scripts/security/tamper/deployments_ledger.csv`, which `known_deploy_ids()` reads;
the next run reports `50 recent deployments checked, 0 unexpected`.

## 3. Why every run said the site was tampered with

`trendi-site/deploy_known_good/` was last promoted on **3 Nov**. The site was
redeployed from this repo after the 9 Nov Concierge cutover, so the old snapshot
differs from live by 90+ files (new logo, products.js, refresh.js, site-i18n,
concierge widget, copy changes).

Proof it is the baseline, not an attack: comparing live against `website/` in this
repo, after stripping only Cloudflare's own injected beacon/challenge loader and
its literal `'nonce-{CSP_NONCE}'` CSP placeholder, gives:

```
ok 107/107 files byte-identical to deployment repo 7c8b113 (website/) with expected security headers
LIVE-INTEGRITY: PASS  (fail=0 warn=0)
```

All redirect/status probes pass (`www` -> apex 301, `/shop` and `/wp-login.php` 410,
config files 404, http -> https 301).

## 4. Defects fixed in this session (each with a failing-before test)

| # | Defect | Cause | Fix |
|---|---|---|---|
| 1 | Nine sections reported "not checked (no token scope)" even after the token gained the scopes | `NOT_SCOPED` was a hard-coded list from the old token | Removed the list. A section the API 403s is INFO "not checked (token cannot read)"; any other absence is UNCHECKED |
| 2 | An unreadable Pages API was reported **OK** for "Pages deployments" | `cf-snapshot.js` wrote `deployments: []`, and the watch treated an empty list as "no unexpected deploys" | Snapshot omits the key and records an error; watch reports UNCHECKED on a missing/empty list |
| 3 | `zone_settings` and `rulesets` showed false CHANGED when one sub-resource 403'd | Missing Universal SSL key and unreadable redirect ruleset were diffed as removals | Partial sections are marked and excluded from the diff; report says what was not compared |
| 4 | Cloudflare's injected challenge script and CSP nonce were counted as site content changes | Stripper only knew the analytics beacon | Strip the exact challenge loader and the literal nonce placeholder too; a real CSP/source change still fails |
| 5 | `accept` could bless a partially read section | State was written after filtering; no guard | State now keeps the raw observation, `_meta.json` records partial sections, and `accept` refuses those sections |

Also fixed: `run-snapshot.sh` resolved a relative output path after `cd`-ing into
the kit, so `run-snapshot.sh out.json` wrote to the wrong directory.

## 5. Evidence

- Python: `python3 -m unittest discover -s tests` → **10 tests, OK**.
- JS: `node tests/test_snapshot.js` → **6/6 checks passed**.
- Mutation checks: reverting each fix turns its test red —
  deployments guard, 403-as-INFO, ruleset filter, nonce normalisation,
  accept refusal, snapshot `rules_unreadable`, snapshot omitted deployments.
- Live run: `daily-watch.sh --cf-snapshot outputs/cf-snapshot-2026-11-17-v3.json`
  → exit 1 (DNS + reviewed config drift only). Live site OK; Pages project OK;
  `50 recent deployments checked, 0 unexpected`.
- Snapshot: 12 sections, 4 errors (all 403/absent-scope, no 5xx).
- **Container run (the real scheduled path):** Hermes now mounts the kit at
  `/opt/data/concierge/scripts/security/tamper` (ro) and `website/` (ro), sets
  `TRENDI_SITE_ROOT=/opt/data/concierge`, and writes reports to
  `/opt/data/.workwatch/reports/tamper`. Inside `hermes-concierge`,
  `run-snapshot.sh` (token from the mounted 0600 copy) → 12 sections;
  `daily-watch.sh` → exit 1 with only the reviewed flags, report written. This is
  why the previous routine path could never have worked: the job runs in the
  container, which cannot see `/Users/jo` or the Keychain.

## 6. Open items (why the job is still paused)

1. **DONE:** Pages Read added; Pages project + deployments check run (0 unexpected).
2. Optional completeness: **Zone** SSL and Certificates Read (the Account variant
   does not cover `/zones/:id/ssl/universal/settings`), **User Details Read**, and
   whichever permission opens the redirect ruleset detail. Until then those are
   reported as not checked, never as changes.
3. **Confirm the mail DNS/DMARC change** before baselining it: MX moved to
   `route1/2/3.mx.cloudflare.net`, DKIM `cf2024-1._domainkey` added, DMARC
   `p=none` -> `p=quarantine`, SPF `include:_spf.mx.cloudflare.net`. This is
   consistent with the documented Cloudflare Email Routing inbound path
   (`INBOUND_EMAIL_SECURITY_2026-11-11.md`, `EMAIL_ASSESSMENT_2026-11-12.md`) and
   DMARC quarantine was noted there as an operator decision — but JOBS T1 still
   requires Jo's explicit yes.
4. Review and accept/reject the other baseline diffs: min TLS 1.0 -> 1.2, WAF
   `api-robots` widened to 60/10 s and scoped away from `/api/v1/*`, "Block AI
   training crawlers" rule, Worker scripts list now empty (routes still point at
   `trendi-force-https`; `/api/robots` is 404 — likely removed in the cutover, needs
   a yes), Page Shield enabled, two billing-budget notifications.
5. Resume the cron job after 3-4; run it once by hand.

## 7. Files

- Kit moved to `scripts/security/tamper/` (was only on the Mac at
  `~/OpenBot/Shared/workwatch/tamper-watch/security/`); `website/` is the known-good.
- `hermes/runtime/start-master.sh` mounts the kit + `website/` read-only and sets the
  report dir; `hermes/routines/trendi-tamper-watch.md` uses the container paths.
  `hermes/JOBS.md`, `hermes/README.md`, `hermes/schedules.yaml`,
  `hermes/scripts/parity_check.py` point at the repo path.
- Reports are gitignored; baselines and `ACCEPT-LOG.txt` stay versioned.
