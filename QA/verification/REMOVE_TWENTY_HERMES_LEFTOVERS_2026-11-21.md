# Remove Twenty backups and Hermes leftovers (2026-11-21)
Order from Jo: "get rid of it, we removed Twenty CRM and we don't use Hermes".
- Cause: dead Twenty backup scripts (docker + Twenty containers, fail closed) and Hermes tables/keys/images/files left behind.
- Fix: removed concierge-stack backup/restore/schedule scripts; Mac launchd plists moved to ~/Archive/removed-20261121/;
  migration 0002 drops hermes_* (empty on production); schema.sql no longer creates them; Hermes label removed from
  OwnerDesk.tsx and owner.html; morning brief report path no longer under reports/hermes;
  box cleanup in scripts/vps/remove-hermes-leftovers.sh; dump via hermes-db-backup.sh; migrate via migrate-api.sh.
- Proof: api/tests/test_hermes_removed.py (mutation-checked); full suite 1558 passed; seo-gate PASS.
- Not touched: dev-* Twenty containers on the box, scripts/vps backups, lane report inputs under ~/.workwatch/reports/hermes.
