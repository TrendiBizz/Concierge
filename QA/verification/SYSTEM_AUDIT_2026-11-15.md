# Full system audit — 2026-11-15 (late session)

Requested: "do a full audit of system and report". Everything below was measured on the live box
and the live sites, then fixed where the fix was ours. The rule was applied: every defect fixed,
tested (mutation-checked), documented here, and deployed in this session.

Scope: host and containers, the deployed API and its parity with `main`, every live owner route,
the Studio in a real browser (light, dark, 390px), the marketing site (39 pages), TLS, firewall,
secrets, backups and restore, alerting/health checks, and the ops scripts we run by hand.

## 0. Verdict

| Area | State after this session |
|---|---|
| Containers | 14 up, api healthy, social reachable from api, 0 tracebacks / 0 5xx in the last 2h |
| API parity | all 105 `api/app/*.py` byte-identical to `main` (md5 diff, 0 differences) |
| Tests | 1299 passed (was 1276 at session start) |
| Owner routes | 64 GET routes answer, 0 × 5xx, 0 empty 200 bodies (OpenAPI rebuilt, then probed live) |
| Studio | 17/17 tabs load, one h1 each, 0 console errors, 0 overflow — light, dark, 390px |
| Marketing site | 39/39 pages 200, 1 h1 each, 0 console/CSP errors, 0 broken links/anchors, widget works — **checkout prices wrong, see §6** |
| TLS | wildcard `*.trendibizz.com`, LE, expires 2027-01-22 (68 days) |
| Firewall | public TCP = 22 only; DB/Redis/AMI/Docker API not listening; **RTP UDP range still open, see §7** |
| Backups | **were broken since 13 Nov; now fixed and a fresh snapshot exists** (2026-11-15T01:43Z) |
| Health checks | 41 ok / 1 warn (sms:inbound, expected) / 0 fail — now includes backups and the SIP firewall |

## 1. Studio: invitation sign-in crashed with React #310 (fixed)

Cause: `Shell()` declared `const [folded, setFolded] = useState(...)` **after** its
`if (!token) return <Login/>` early return. When the invitation flow set a token the hook count
changed between renders and React threw #310 ("Rendered more hooks than during the previous
render"), which the ErrorBoundary caught and logged as "Studio page failed:".

Evidence: headless Chromium on the live invite link, `Error: Minified React error #310 … at
e.useState`. Every new owner's first screen after clicking their link was the error boundary; a
reload (token now in localStorage) then worked, which is why nobody had reported it.

Fix: the state moved above the early return. Guard: `test_every_hook_is_declared_before_the_signed_out_return`
(mutation → red). Live: invite link now lands on Home with 0 console errors.

## 2. `/studio/<missing file>` answered 200 HTML (fixed)

Cause: the catch-all route served `index.html` for every unreadable path, so the old worker URL
`/studio/sw.js` returned 200 `text/html`. A browser still holding the old worker fetches it for an
update, rejects it on the MIME type, and the stale worker can never be replaced — the exact class of
bug §6l was meant to end. The previous record claimed this URL 404'd; it did not.

Fix: a missing path with a dot in its last segment is a 404; only a real app URL gets the shell.
Guard: `test_a_missing_file_is_a_404_not_the_app_shell` (mutation → red). Live: `/studio/sw.js` →
404, `/studio/robots.txt` → 404, deep app URL → 200.

## 3. The Settings group needed two clicks (fixed)

Cause: the visible state is `folded[group] ?? default`, with Settings defaulting to folded. The
toggle computed `!folded[group]` = `!undefined` = `true`, so the first click wrote "folded" again
and nothing happened. Setup, Channels and permissions, Team, Your CRM and Saved replies were
unreachable until the header was clicked twice.

Fix: `toggleGroup(name, hidden)` flips the state actually being rendered. Guard:
`test_the_folded_settings_group_opens_on_the_first_click` (mutation → red). Live: one click,
`aria-expanded=true`, 17 nav items, localStorage `{"Settings":false}`.

## 4. Companies and Saved replies had no page heading (fixed)

Both tabs are missing from `HERO`, so the shell rendered no `<h1>` on those pages. Added entries;
guard `test_every_navigation_tab_has_a_page_heading` (mutation → red). Live: 17/17 tabs have exactly
one h1.

## 5. The Studio scrolled sideways on a phone (fixed)

Measured at 390px: document 435px wide on **every** tab (45px of horizontal scroll), sidebar a
fixed 217px column, and `.c-nav { display: none }` meant a phone had no navigation at all.
Root cause: the `@media (max-width: 900px)` block sat **before** the base `.c-nav` rule, so the base
rule won at equal specificity. The earlier `grid-template-columns` override that "never applied"
had the same cause.

Fix: the media block moved to the end of `shell.css`; the shell is one column, the brand/topbar/nav
stack, and the navigation wraps into a height-capped, internally scrollable strip (wrapping 17 items
without a cap pushed Reports to y=918 in an 844px viewport). Guards:
`test_the_shell_has_no_horizontal_scroll_on_a_phone`. Live 390px: scrollWidth 390, 17/17 tabs
clickable, 0 console errors. Light and dark at 1440px: 17/17, 0 errors, 0 clipped tables.

## 6. The API image contained the VPS root SSH private key (fixed)

`/srv/app/Concierge` existed inside the running API container, mode `-rw-r--r--`, first line
`-----BEGIN OPENSSH PRIVATE KEY-----`: the deploy's root key had been copied into `api/app/` in the
release tree and baked into the image. The API runs as root in that container, so any code execution
would have handed over root on the host.

Fix: the stale copy was removed from the release tree by the code rsync, both `.dockerignore` files
now exclude key material, the image was rebuilt, and the running container no longer has the file.
Guards: `test_no_private_key_material_is_in_the_build_context` and
`test_the_docker_ignores_exclude_key_material` (planting a key turns them red).

Still open (operator): the key itself has been readable in that image since 8 Nov, so rotation is
the only complete remedy — see §8.

## 7. Encrypted backups had been failing for two days (fixed)

Cause: `backup.py` dumped `trendi-crm-db-1` unconditionally. The Twenty CRM stack runs under the
compose `crm` profile and is intentionally stopped, so from 13 Nov every run died with
`container … is not running` **before** restic uploaded anything. Last snapshot: 12 Nov 14:15Z.
The health check had no backup check at all, so the report said ok.

Fixes: optional parts are skipped and recorded in `backup-manifest.json`, the Concierge database can
never be skipped, the legacy `backup-all.sh` does the same, and `restore-drill.sh` (absent from the
release, so the weekly cron had never done anything) is deployed. New health checks `backup:age`
(warn > 26h, fail > 50h) and `backup:service` (systemd exit state).

Evidence: `trendi-backup.service` → `{"ok": true, "skipped": ["database default skipped: …",
"crm storage, redis and Twenty data skipped: …"]}`; `restic snapshots` shows
`b0731b55 2026-11-15 01:43:56 trendi-vps trendi-vps`; `backup-all.sh` produced
`trendi-backup-20261115-014510.tar.gz` (34 MB); `restore-drill.sh` recovered
`businesses=4 enquiries=27 quotes=0 messages=49 users=4` into a scratch database and dropped it, and
`/opt/trendi/backups/restore-drill.log` now exists. Tests:
`test_a_stopped_crm_profile_is_skipped_not_fatal`, `test_the_core_database_can_never_be_skipped_silently`,
`test_a_missed_daily_run_warns`, `test_two_missed_days_fail` (each mutation-checked).

## 8. Ops scripts: env file, health URL, SIP firewall (fixed)

- `check-inbound-chain.sh`, `rotate-cloudflare-token.sh` and `order-phone-did.sh` sourced
  `/opt/trendi/shared/api.env`. `ASTERISK_CHANNEL_DIAL=PJSIP/<number>@concierge` is a shell
  redirect, so every cron run printed `number: No such file or directory` and the variable silently
  became `PJSIP/`. New `scripts/vps/env_lib.sh` reads the file as data; guards in
  `test_vps_scripts_env.py` (mutation → red).
- The same rotate script checked `https://chat.trendibizz.com/healthz`, which is a documented 404
  through Cloudflare, so it warned about a healthy API. It now checks `127.0.0.1:8000/healthz` on
  the box.
- `trendi-sip-firewall.service` was enabled but **dead**, so the UDP/5060 DROP existed only because
  the rules had been applied once. It is now started (`--now` is in `harden_host.sh`) and a new
  `sip:firewall` check fails if the unit is not active or the `TRENDI-SIP` chain has no DROP.
- `crontab.txt` now records the systemd timers too, and the 14:30 cron line points at the release
  copy of `backup-all.sh` (the old `/opt/trendi/backups/backup-all.sh` copy was the broken one).

## 9. Hygiene done

- Deleted `/opt/trendi/shared/api.env.bak-20261112-073338` and `…-prewhsec` (the latter still held
  the pre-rotation Stripe webhook secret plus AMI/Twilio/Cloudflare/VAPID values).
- Pruned old `trendi-concierge-api:before-*` images.
- Health check now 41 ok / 1 warn / 0 fail (`ok` was 39).

## 10. Found but NOT ours to fix (operator decisions)

1. **Stripe charges GST on top of the advertised price.** Measured by opening the checkout with
   fields empty: Concierge monthly advertises USD $250 and the checkout says "$287.50 per month …
   Apply GST (15%) $37.50"; yearly advertises $2,700 and says "$3,105.00"; SEO monthly $1,500 →
   $1,725; deposit $1,000 → $1,150. No page on the site mentions GST at all (0 hits across 39
   pages). Either the Stripe prices must be tax-inclusive or the advertised figures are wrong.
   Only the Stripe dashboard can change this.
2. **Yearly is contradictory.** `/pricing` sells yearly publicly (USD 3,105 checkout), while
   `products.js` keeps the yearly link deliberately empty ("available after the first three
   months") and the copy says the same; `/concierge-start?plan=yearly` has no purchase path at all.
   Decide which is true, then make the copy and links agree.
3. **Stripe business name** differs between links: "Trendi Limited" (Concierge) vs
   "Trendibizz.com" (SEO/deposit).
4. **Rotate the VPS root SSH key** and the **live Stripe secret key** (`stripe.key` /
   `api.env`): the key sat in the API image (§6) and a secret was printed into an audit transcript
   this session by a sub-agent's redaction mistake.
5. **UDP 10000–10099 (RTP) is reachable from the internet.** Docker DNAT bypasses ufw; only 5060 is
   filtered. This was a documented trade-off (a media gateway on another address must not cause
   one-way audio). If calls with the carrier are verified, the exact closing rules are in the header
   of `scripts/vps/harden_host.sh`.
6. **containerd holds ~65 GB** of old images; disk is 47% used. `docker image prune` of the
   remaining `before-*` tags (keep 2–3) reclaims most of it.
7. `/opt/trendi/releases` is world-readable and embeds ~32 test DSNs and one `whsec_` in test
   fixtures; several containers still run as root without `no-new-privileges`.
8. `/var/run/reboot-required` is set (unattended upgrades). Reboot in a window and confirm the SIP
   firewall service comes back active.

## 11. Reproduce

```
cd api && TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres python3 -m pytest -q
# 1299 passed

ssh -i ./Concierge root@152.42.239.240 \
  'docker exec trendi-api-1 ls /srv/app/Concierge; systemctl is-active trendi-sip-firewall.service;
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:8000/studio/sw.js;
   systemctl start trendi-backup.service && journalctl -u trendi-backup.service -n 3 --no-pager'

# Studio, 17 tabs, three viewports: /tmp/audit_studio4.mjs (throwaway script this session)
```
