# Studio sales pipeline board + Twenty CRM retired — 2026-11-17

## What was asked

Jo: "retire twenty and build the sales style kanban opportunity board please and include it, the twenty
crm can be deleted entirely we have never used it."

Two pieces: (1) delete the Twenty CRM completely, and (2) a drag-and-drop sales board in the Studio.

## Twenty CRM: deleted entirely

The Twenty stack was never used (its containers had been stopped for days; its database was ~24 MB of
Twenty schema with an empty file store). Nothing was migrated.

Removed:

- `scripts/vps/compose.yml`: the `crm` profile (`crm-db`, `crm-redis`, `crm`, `crm-worker`) and the
  `crm-database`/`crm-redis`/`crm-storage` volumes.
- `docker-compose.yml` (local dev): the `twenty` and `twenty-worker` services, the `x-twenty-env`
  anchor, the `twenty_storage` volume and the `crm` profile example.
- `docker-compose.twenty-bridge.yml`, `integrations/twenty/` and `scripts/export-twenty-bridge-key.sh`.
- `api/app/events.py`: the whole Twenty delivery queue (`twenty_bridge_payload`, `queue_twenty`,
  `process_twenty_once`, `run_twenty_forever`); the general lead webhook stays.
- Its call sites in `automation.py`, `voice_records.py` and `asterisk_bridge.py`; the lifespan worker
  in `main.py`; the `twenty_bridge_*` settings in `config.py`.
- `concierge-stack/agent/crm.py` and the two `crm.push_lead(...)` calls in `agent.py`.
- `api/app/schema.sql`: the `twenty_deliveries` table, replaced by `DROP TABLE IF EXISTS
  twenty_deliveries` so a running box cleans it up on the next start.
- Backup/ops: `backup.py` no longer dumps the CRM; `backup-all.sh`, `restore-test.py`, `backup.sh`,
  `gen-env.sh` and `auto-end-session.py` lost their Twenty references; the optional-CRM backup test
  now asserts the CRM logic is gone.
- On the box: the `trendi_crm-database`, `trendi_crm-redis` and `trendi_crm-storage` volumes, from both
  Podman and `/var/lib/docker`. Production stayed 200 before and after.

Not touched on purpose: the Rust port's Twenty parity module (`concierge-stack/core-rs`) is a separate
self-contained implementation, and the `dev-concierge-twenty-*` containers are local dev. Both are
follow-ups, not the production CRM.

## The board

The five stages already existed (`new → contacted → booked → won → lost`, `sales.py`), so the board is a
view over that engine, not a second pipeline:

- `GET /owner/crm/pipeline` returns `sales.pipeline(tenant)` — the same grouped counts, per-stage value
  and weighted forecast the admin dashboard and the weekly summary read.
- `POST /owner/crm/leads` adds an offline opportunity (a walk-in/referral) to the `new` column.
- `web/portal/src/Pipeline.tsx`: a drag-and-drop board (all five columns, per-column count and value,
  open/weighted/won summary, search, a "New opportunity" form). Cards also carry a stage menu, so it
  works on touch where HTML5 drag-and-drop does not. Registered in Studio → Sales → Pipeline.

## Proof

- API suite: **1523 passed, 19 skipped** (was 1521 passed + 2 failing before the fixes below).
- New tests `api/tests/test_pipeline_board.py` (3): stage grouping + weighted forecast, tenant-scoped
  create, unknown tenant → 404.
- Portal: `tsc -b` exit 0, `vite build` exit 0, `oxlint src/Pipeline.tsx` clean.
- Both compose files parse as YAML.
- `verify-deploy.sh` (below), and the box's crm volumes are gone.

## Defect found and fixed while doing it

The new nav tab failed `test_every_navigation_tab_has_a_page_heading` (every tab must have a `HERO`
title) — added `pipeline` to `HERO`. And the backup test asserted the old "skipped CRM" behaviour;
updated to assert the CRM logic is actually gone (mutate-proof: the old assertions fail against the new
`backup.py`).
