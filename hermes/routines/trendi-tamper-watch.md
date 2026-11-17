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
   `~/.config/trendi/cloudflare_token` is a copy. Inside the container there is no
   Keychain, so `run-snapshot.sh` reads the mounted copy
   `/opt/data/.config/trendi/cloudflare_token`; on the Mac it reads the Keychain.
2. The tamper kit, mounted read-only at
   `/opt/data/concierge/scripts/security/tamper/` (`website/` is the known-good; the
   old `trendi-site/deploy_known_good` snapshot is stale since the 9 Nov cutover).
   Reports go to `/opt/data/.workwatch/reports/tamper/`; baselines are read-only in
   the container, so `accept` is a Mac-side action.
3. A working snapshot runner: `run-snapshot.sh` (Keychain -> env -> GET-only
   `cf-run-snapshot.js`). Do not hand-roll an API call or print the token.

If any prerequisite is missing: write `Status: blocked` with the exact missing item
and stop. Do not improvise a snapshot or accept a baseline.

## Procedure

Run the watch (read-only; never change Cloudflare, DNS, the registrar or the site).

1. Take a Cloudflare snapshot with the kit's runner:
   `bash /opt/data/concierge/scripts/security/tamper/run-snapshot.sh /tmp/cf.json`.
2. Run:

   ```bash
   bash /opt/data/concierge/scripts/security/tamper/daily-watch.sh --cf-snapshot /tmp/cf.json
   ```

   and read `/opt/data/.workwatch/reports/tamper/daily-watch-latest.txt`. Usage and
   the accept command are in
   `/opt/data/concierge/scripts/security/tamper/README.md`.
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

Write to `/opt/data/.workwatch/reports/hermes/site-watch/<date>-trendi-tamper-watch.md` and
update `latest.md`. A clear day is `Status: quiet` and nothing else. A flag is
`Status: attention` with the section, the before/after and the evidence.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/site-watch/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/site-watch/<YYYY-MM-DD>-trendi-tamper-watch.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# trendi-tamper-watch — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/site-watch/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
