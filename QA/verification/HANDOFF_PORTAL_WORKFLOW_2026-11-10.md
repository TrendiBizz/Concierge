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
2. **Knowledge for the second business** — `trendi-meta-review` has 0 chunks, so its
   assistant cannot answer from its own information yet. Customer content, not code.
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

Items 2, 3 and 6 are customer data or consent; item 1 is one authorisation; items 4
and 5 are separate optional gates.

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

   Nothing was changed. To finish this, the options are (a) use the UI's default-mode
   control, which needs no code, or (b) confirm the config key that feeds
   `sandboxPolicy.defaultMode` so it can be set in `~/.dsh/cordis.patch.yml`. Option
   (a) is recommended: it is the supported path, and it cannot corrupt session state.
2. **Automatically end long sessions and run commit/push/handoff.** Not built. Needs
   two decisions: the trigger (turn count, context size, or elapsed time) and whether
   pushing to `main` is automatic or waits for review.

## Working notes for the next session

- **Use bind mounts, never `docker cp`, to test code against production.** This
  session copied files into the running API container, contaminating it; the mistake
  was caught by hashing the container against its image and cleared by recreating it.
  Verify that hash after any such work.
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
