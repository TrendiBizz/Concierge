# Concierge handoff — session 2026-11-10 (portal workflow verification)

Read `HANDOFF_CURRENT_DEPLOYMENT_2026-11-10.md` for deployment mechanics and
`HANDOFF_CONCIERGE_PORTAL_WORKFLOW_2026-11-09.md` for the full seven-requirement
mandate. This document records what was verified, the five defects found and
fixed, and exactly what remains.

## Objective

Verify and complete the seven-step business-specific portal secretary workflow on
current main: receive voice/text/email; identify channel; answer from the
business's own information; forward the original enquiry to the right owner;
offer an optional acknowledgement to the enquirer, kept separate from owner
alerts; retain the full CRM dialogue and turn agreed bookings into owner-calendar
entries plus enquirer invitations; provide CRM Quotations.

Never fabricate delivery, calendar success or test results. Cellular SIP is an
optional separate gate and was not touched.

## Repository and deployment state

| | |
| --- | --- |
| Workspace | `/Users/jo/work-staging/concierge-integration` (git worktree) |
| Branch | `main`, HEAD `12d244e`, matches `origin/main` (0/0) |
| Tests | **470 passed** (`PYTHONPATH=api pytest api/tests -q`) |
| Rust | `GATE-ALL-OK` (`./scripts/rust-gate.sh`) |
| Deployed image | `trendi-concierge-api:vps` → `51731df49bd3` |
| Container matches image | yes — verified by hashing `/srv/app/**/*.py` both sides (`153a9382…`) |
| Rollback tags | `before-sms-throttle-20261110`, `before-clean-rebuild-20261110` → `c69687f6bf10`, `before-calendar-time-tolerance-20261110` |
| Backups | `/opt/trendi/backups/sms-throttle-20261110`, `.../clean-image-rebuild-20261110`, `.../rollback-drill-20261110` |

Production tenants (3): `concierge` (archived prototype), `trendi-oauth-staging`
(Trendi Concierge, owner `admin@trendibizz.com`, 28 chunks, 1 calendar, no opening
hours), `trendi-meta-review` (Meta review workspace, owner
`meta-review@trendibizz.com`, 5 weekdays 09:00–17:00, no calendar, no knowledge).
One appointment, one quotation.

## The five defects found and fixed

1. **Invisible booking readiness** — an owner could not tell why booking was
   disabled. `owner_onboarding.booking_readiness()` now returns a reason, surfaced
   as `channels.booking` in the portal.
2. **Permissions panel rendered 1 of 7 controls** — `refreshChannelAuthorizations()`
   dereferenced `readiness.channels[key]` unguarded and threw `TypeError`, and
   `Promise.allSettled` swallowed it. Now uses safe access; all seven render.
3. **Calendar time comparison stranded bookings** — `sync_one` compared provider
   timestamps exactly, but Google truncates microseconds, so every booking stayed in
   `retry` forever. Now tolerates <10s. Deployed and proven live.
4. **Gateway blocked a route the API served** — `/api/v1/phone/managed/*` was absent
   from the gateway's owner route, so the carrier webhook returned 404 at the edge
   while working at origin. Fixed and deployed.
5. **A conversation texted the owner once per turn** — the most serious, because it
   visibly reached the owner. Dedupe keys deliberately include the message text, so
   `ON CONFLICT DO NOTHING` never collapsed distinct turns: one test enquiry produced
   **54 owner SMS** (28 enquiry + 26 dialogue). `owner_notifications.queue` now
   coalesces alerts for the same lead and channel while an earlier one is still
   undelivered (`owner_alert_min_interval_seconds`, default 300; 0 disables). Fixed,
   deployed, and the regression test fails without it.

## Verification performed (all against real systems)

- **Two-business isolation and booking** — re-proven this session against real Google:
  the second business offered 16 slots from its own Chicago hours, the event synced,
  and the provider recorded *that* business's tenant marker and attendee. Cleanup 204;
  calendar re-checked at its one-event baseline.
- **Acknowledgement through the assistant's own tool** — offer queues nothing,
  confirm queues exactly one, decline records without sending, the worker delivers,
  and it stays `enquirer_ack` rather than `owner_alert`.
- **Rate limiting is per visitor** — exhausting one visitor gave 429 while a second
  visitor still got 200, so one person cannot block everyone.
- **Widget** — served bytes match source, parses, all six endpoints exist, loads and
  registers against a DOM stub. CORS verified: `access-control-allow-origin: *` on
  success, with the owner APIs deliberately same-origin only.
- **Owner portal and admin pages** — element ids resolve, scripts parse and load, all
  portal refresh functions and every called endpoint exist. Admin is intentionally not
  routed publicly.
- **Calendar `.ics`** — valid VCALENDAR at origin and through the gateway.
- **Rollback drilled on production** — rolled back and forward, data intact, with the
  trap recorded that re-tagging an image can silently restore the wrong build.

Reusable checks live in `QA/verification/`: `gateway_route_audit.sh` +
`gateway_route_list.py` (96 routes reach the app), `owner_ui_check.mjs`,
`widget_check.mjs`, `admin_ui_check.mjs`. Each was confirmed able to fail.

## What remains

1. **One Google OAuth consent** for `meta-review@trendibizz.com`. Only the account
   holder can grant it, and it is the difference between a second business having a
   permanent calendar connection and borrowing the first business's. Two businesses
   sharing one Google account interfere, because `busy()` queries per `calendar_id`
   fixed to `'primary'`.
2. **Knowledge for the third business** — `trendi-meta-review` has 0 chunks, so its
   assistant cannot answer from its own information yet. Customer content, not code.
   (Corrected 2026-11-10: the 28 chunks belong to `trendi-oauth-staging`, not to the
   business that needs them. See "Correction" below.)
3. **An enquirer acknowledgement reaching a real person** — the whole path is verified
   against a real database, but no acknowledgement has gone to an actual enquirer,
   because that needs their consent.
4. **Inbound SMS end to end** — no provider configured, routes return 503 by design.
   The device is online but `inbound_verified_at` is NULL. Owner **email** reached
   `sent` on every attempt.
5. **Cellular SIP / real carrier calls** — optional and untouched. `phone_numbers = 0`.
6. **Opening hours for `trendi-oauth-staging`** — empty, so booking correctly refuses
   with "No opening hours are set, so booking would offer no times on any day". An
   owner data-entry gap the readiness entry now makes visible before they try.
   **This one is correct** — verified live 2026-11-10:
   `trendi-oauth-staging` has all seven days empty.

Items 2, 3 and 6 are customer data or consent; item 1 is one authorisation; items 4
and 5 are separate optional gates.

## Correction (2026-11-10, next session)

Two errors in this document were found and fixed. Both were in the summary I wrote,
not in the work itself.

**1. The hours finding was transplanted between businesses.** The final readiness
check of the previous session printed, at seq 7401:

```
trendi-oauth-staging   open_days=0   reason: No opening hours are set...
trendi-meta-review     open_days=5   reason: (empty — booking hours are fine)
```

Item 6 above is a faithful copy of the first line. But the two-business narrative
elsewhere in this document describes `trendi-meta-review` as the one lacking hours,
and that is what a reader takes away. Live state confirms which is which:

| Tenant | business_hours | chunks |
| --- | --- | --- |
| `concierge` | Mon–Fri 09:00–17:00 | 0 |
| `trendi-meta-review` | Mon–Fri 09:00–17:00 | **0** |
| `trendi-oauth-staging` | **all days empty** | **28** |

So: `trendi-oauth-staging` owns the missing hours *and* the 28 chunks, while
`trendi-meta-review` has hours but no knowledge. Items 2 and 6 had been attached to
the wrong businesses relative to the narrative that used them.

**2. "3 tenants / 28 chunks" was measured on the VPS, not locally.** The previous
session did all its database work over SSH to `root@152.42.239.240` (container
`trendi-postgres-1`). This session first queried the *local* `concierge-postgres-1`
and saw 2 tenants and a different chunk layout, and briefly concluded production
had diverged. It had not. Local and VPS are separate databases; three tenants is
correct on the VPS:

```
ssh root@152.42.239.240 → trendi-postgres-1 / concierge
  concierge | trendi-meta-review | trendi-oauth-staging
```

The lesson is the one already in the working notes below, applied to myself: a
query that returns a plausible-looking answer from the wrong host is not evidence.
Ask which host the answer came from.

**3. Requirement 7 (CRM Quotations) has no table in the local database.** On the
VPS, quotations exist and the previous session verified them (orphan count 0 after
cleanup, and a quotation visible to one business and not the other). The local
`concierge-postgres-1` simply is not that database. Same root cause as (2).

## Completed this session (2026-11-10, next session)

**Opening hours for `trendi-oauth-staging` — DONE.** Set to Mon–Fri 09:00–17:00,
closed weekends (the same table the other two businesses use), written through
`tenants.update`, not raw SQL, so it passed the app's own validation.

| | before | after |
| --- | --- | --- |
| `open_days` | 0 | **5** |
| readiness reason | "No opening hours are set…" | `''` (cleared) |
| `native_booking` | false | false (**deliberately unchanged**) |

Verified twice: once by the writing script's own read-back, then again by an
independent SQL query, because a script confirming its own write is not evidence.

Backup of the `tenants` table taken first, to
`/opt/trendi/backups/hours-write-20261110/tenants-before.dump`.

**Orphaned Google tokens — cleaned.** `calendar_connections` has **no token
column**; tokens are files in `/run/concierge-calendar/<tenant-uuid>.json`. The
10 fake tenants deleted after the accidental production write had their DB rows
cascade away, but **their token files did not** — so 8 credential files remained
for tenants that no longer exist. Moved (not deleted) to
`/opt/trendi/backups/orphan-calendar-tokens-20261110/`. The directory now holds
exactly `0a3e7155….json` (`trendi-oauth-staging`) and `google-app.json`.

**Which businesses actually have a calendar, verified:**

| Tenant | Google token |
| --- | --- |
| `trendi-oauth-staging` | **yes** — refresh token + calendar scope |
| `concierge` | no |
| `trendi-meta-review` | no |

This is why the OAuth item is not merely a formality: `finish()` writes that file
only after a real Google redirect as the account holder. Two of the three
businesses have no calendar credential at all.

## Open asks from the owner (not yet done)

1. **Persist full-access permissions across sessions.** The cause is now established
   with evidence rather than guessed.

   DSH records the sandbox mode as **per-session state**, not as global configuration.
   Each session file under `~/.dsh/storages/session_projcache/sessions/*.json` carries
   its own row:

   ```
   <session>  record.rows.sandboxMode = {"ver":1,"seq":3335,"val":"danger-full-access"}
   ```

   and a case-sensitive search for `sandboxMode` across `~/.dsh/` finds it **only** in
   those per-session files — nothing global, nothing in `cordis.patch.yml`, and
   `dsh dump-config` resolves no sandbox key at all. That is exactly why the choice
   resets: a new session starts with no row and falls back to the deployment default.

   So the fix is not to edit a config value that is merely unset; it is to give DSH a
   **default for new sessions**. The permission UI describes exactly that setting
   ("Choose the default permission mode for new sessions"), which means the supported
   route is that control, not hand-editing session JSON. Hand-editing session files
   would be wrong twice over: it sets one session rather than the default, and it
   writes into state DSH owns.

   **DONE 2026-11-10.** Option (b) as written was wrong: no `sandboxPolicy.defaultMode`
   key exists anywhere in the harness. The real mechanism is `defaultPreset` on the
   loader entry whose id is `permission` (`@deepseek-ai/dsh-permission-presets`).
   Applied to `~/.dsh/profiles/web/cordis.patch.yml`:

   ```yaml
   - id: permission
     name: "@deepseek-ai/dsh-permission-presets"
     config:
       defaultPreset: workspace-write
   ```

   Verified by `dsh --profile web --dump-config`: the entry is marked
   `patched by …/cordis.patch.yml` with `defaultPreset: workspace-write`, and no
   patch warnings. The UI route is the *same* write, not an alternative — the
   General settings row mutates namespace `permission`, path `["defaultPreset"]`.
   `defaultPreset` is consulted only for a genuinely fresh session
   (`!seeded`), so existing sessions keep their pinned knobs and cannot be
   rewritten. Backup: `cordis.patch.yml.bak-20261110-150553-preperms`.
   Takes effect for sessions created after the web profile restarts.
2. **Automatically end long sessions and run commit/push/handoff.** Still not built,
   but **decided**: trigger is context size, push is automatic to `origin/main`.
   Full design including the `contextPressure` vs lifetime-`tokenUsage` trap, push
   guardrails, and acceptance criteria:
   `SPEC_SESSION_AUTOEND_AUTOPUSH_2026-11-10.md` (this directory).

## Working notes for the next session

- **Every database claim in this document is about the VPS, not the Mac.** The work
  is done over `ssh root@152.42.239.240` against container `trendi-postgres-1`,
  database `concierge`. The Mac's `concierge-postgres-1` is a *different* database
  with a different tenant list and no `quotations` table. State which host a query
  ran on, or the next session will compare two different systems and conclude the
  data has diverged when it has not.
- **Use bind mounts, never `docker cp`, to test code against production.** This
  session copied files into the running API container, contaminating it; the mistake
  was caught by hashing the container against its image and cleared by recreating it.
  Verify that hash after any such work.
- **The two-business test wrote to production once.** `os.environ["DATABASE_URL"]`
  was set *after* `app.config.get_settings()` had been called, and that function is
  `@lru_cache`d — so the cached production URL was reused and 10 fake tenants
  (`harbour-dental`, `southern-plumbing` and slug-suffixed copies) were created in
  the live database. Cleanup deleted exactly those, backed up first to
  `/opt/trendi/backups/accidental-test-cleanup-20261110/before-cleanup.dump`, and
  all three real tenants were confirmed preserved by predicate check beforehand.
  `QA/verification/twobiz/run_twobiz.sh` now exports the URL *before* Python starts
  so the cache cannot be pre-filled. The lasting lesson: an environment override is
  not an override if something already cached the old value. Assert the resolved URL
  at the top of any script that must not touch production.
- **Repeated failure mode:** a tool reporting nothing is not evidence of absence.
  This session hit it with a missing `strings`, a sort-order mismatch, a host-routing
  404, a regex that skipped empty paths, and a rate-limit response mistaken for a CORS
  problem. Ask what the result would look like if the measurement were wrong.
- **Four tests passed against deliberately broken code** and were caught only by
  trying to falsify them. A test that cannot fail proves nothing.
- Safe probe pattern: create `concierge_twobiz_verify`, load the schema with
  `sed 's/__DIM__/384/g' api/app/schema.sql`, run with `DATABASE_URL` ending in that
  name, drop it afterwards, then re-check production is 3 tenants / 28 chunks.
- Never stage or print the repo-local `Concierge` SSH key or environment secrets.
  Preserved untracked files that must not be committed: the four `HERMES_*` files and
  the `office-shots/` and `tiktok-review/` directories under `QA/verification/`.
