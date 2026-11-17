# Routine: trendibizz.com daily tamper watch

- Profile: `site-watch`
- Schedule: `30 7 * * *` Pacific/Auckland
- Source: Grok Trendi Desk automation `trendibizz-com-daily-tamper-watch`
  (paused 2026-11-06); verbatim prompt in jo-brain
  `profiles-full/trendi-desk-to-openbot-workwatch.md` A
- Status: **paused** — see `JOBS.md` T1
- Approval: read-only; never accepts or reverts by itself

## Prerequisites (check first)

1. A **read-only** Cloudflare API token on the Mac, with DNS, Zone, Zone Settings,
   SSL and Certificates, Firewall and Workers Routes Read; Pages, Workers Scripts,
   Account Settings and Notifications Read; User Details Read. It lives in the
   Keychain item `trendi-cf-readonly-token` — that is what the watch reads;
   `~/.config/trendi/cloudflare_token` is a copy.
2. The tamper kit in `/Users/jo/work-staging/concierge-integration/scripts/security/tamper/`
   (`website/` is the known-good; the old `trendi-site/deploy_known_good` snapshot
   is stale since the 9 Nov Concierge cutover).
3. A working snapshot runner: `run-snapshot.sh` (Keychain -> env -> GET-only
   `cf-run-snapshot.js`). Do not hand-roll an API call or print the token.

If any prerequisite is missing: write `Status: blocked` with the exact missing item
and stop. Do not improvise a snapshot or accept a baseline.

## Procedure

Run the watch (read-only; never change Cloudflare, DNS, the registrar or the site).

1. Take a Cloudflare snapshot with the kit's runner:
   `bash scripts/security/tamper/run-snapshot.sh /tmp/cf.json`.
2. Run:

   ```bash
   bash scripts/security/tamper/daily-watch.sh --cf-snapshot /tmp/cf.json
   ```

   and read `scripts/security/tamper/reports/daily-watch-latest.txt`. Usage and
   the accept command are in `scripts/security/tamper/README.md`.
3. Handle the exit code:
   - **0 (all clear):** stay completely quiet, no message to Jo.
   - **1:** work out whether each flag matches a change recorded in
     `baselines/ACCEPT-LOG.txt`, `QA/verification/`, the jo-brain handover or the
     Cloudflare change log. Expected
     DNSSEC `pending -> active` is approved only with the reason (e.g. "DS added at
     Namecheap"). For anything not clearly approved, treat it as possible tampering:
     tell Jo in one or two plain sentences (what changed and when), and do not accept
     or revert anything yourself.
   - **2:** retry once; if it still cannot check, tell Jo briefly only if it fails two
     days running.
4. Never reuse the old box baselines as truth. Run once, review every flag against the
   ledger, then take fresh baselines. Never accept the mail DNS or DMARC items without
   Jo's explicit confirmation.

## Output

Write to `~/.workwatch/reports/hermes/site-watch/<date>-trendi-tamper-watch.md` and
update `latest.md`. A clear day is `Status: quiet` and nothing else. A flag is
`Status: attention` with the section, the before/after and the evidence.
