# Version 1, owner desk (Needs you / Ask / morning email) and release notices, 2026-11-17

## What shipped
- `api/app/releases.py`: `RELEASES` + `CURRENT_VERSION` (= 1, label "Version 1"). `tenant_users.last_seen_version` records the
  newest notice each person dismissed. Routes: `GET /owner/release`, `POST /owner/release/seen`, public `GET /version` and
  `GET /owner/version`, admin `POST /admin/releases/announce` (preview by default, `send=true` queues one email per business,
  deduped by `release:{version}:{tenant}`).
- `api/app/owner_ask.py` + `POST /owner/ask`: read-only, no tools, answers from the owner's own documents and today's counts.
- `owner_onboarding.daily_summary` (owner can switch the 7am note on/off); `email_drafts.origin='hermes'` labels Hermes drafts.
- Studio (`web/portal/src/OwnerDesk.tsx`, shown on Home): What's new, Needs you (edit/approve/discard), Ask, Morning email;
  footer shows "Version 1". The older `/owner-ui` page (`api/static/owner.html`) got the same panels.

## Defects found on the way
1. **Edited the wrong UI first.** `owner.html` (`/owner-ui`) is the legacy page; customers use the React Studio in `web/portal`
   served at `/studio/`. Studio had no draft approval screen at all. Fix: built it in Studio. Proof: rendered the built bundle against a
   local mock API in a browser: all four cards present, footer "Powered by Trendi · Version 1 · Privacy", Got it / Ask / switch /
   Approve each worked (DOM assertions).
2. **Public edge 404 on `/version`.** `Caddyfile` forwards only an allowlist (`/owner/*` among it). The footer would never have shown
   a version. Fix: also serve `/owner/version`. Proof: `curl https://concierge.trendibizz.com/owner/version` -> `{"version":1,...}`.
   Mutation: removing the route made `test_notice_shows_until_dismissed_then_stays_dismissed` fail.
3. Deployed Studio once before committing (order slip); committed `35f3efd` straight after, rebuilt and redeployed from `0d204ba`.

## Tests and mutation checks
`api/tests/test_release_and_ask.py` (5 tests). Mutants all killed: `unseen` forced True, `dedupe_key=None`, dropping the
`daily_summary` field, passing `tools=` to the LLM, ignoring `dry_run`, removing `/owner/version`. Full suite: 1517 passed, 19 skipped.
Not covered by an automated test: the Studio React components (checked by hand in a browser as above) and the Hermes `origin` label.

## Live proof (box, 2026-11-17)
- 7am note from live data with one labelled test lead on `trendi-support`: subject "Trendi: 1 new in the last day"; a quiet day
  returns nothing. `tenants.daily_summary` for `trendi-support` set to true via the admin API. The test lead was then deleted (0 leads).
- Hermes shadow run on that lead: `mode: shadow, executed: false`, proposed `escalate_case`. Nothing sent, no rows written.
- Release announcement preview (`dry_run`): 4 recipients listed (Pukeko Construction, 3 Trendi tenants), 0 queued. NOT sent.
  To send: `POST /admin/releases/announce?version=1&send=true` with the admin token, after Jo approves the wording.

## Open
- Several tenants share `admin@trendibizz.com`; sending would email that address three times.
- First real 07:00 NZ email for `trendi-support` can only be confirmed tomorrow after 07:00 NZDT (and only if something needs attention).
