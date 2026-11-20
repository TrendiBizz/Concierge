# Hermes removal verification — 2026-11-20

Status: implemented and verified locally. No production deployment, container removal on the VPS, volume deletion, push or live outbound-message test performed.

Removed the tracked Hermes installer/runtime/profile/routine files and deployment scripts. Retained first-party policy, approval and tenant isolation functionality under Concierge action names. The Rust action gateway now calls an explicitly configured model endpoint, with no implicit Hermes endpoint or tool runtime. Updated API imports, settings, internal route/header names, UI attribution, Docker paths, CI references and monitoring footer.

Existing database records are preserved by a lossless legacy-table rename and origin migration. Conflicting old/new tables fail closed for reconciliation. Deployment must coordinate all API writers with the schema change; old processes use the previous table names. Do not drop tables or volumes to upgrade.

Verification:
- Rust core: 128 tests passed. Rust social service: 75 tests passed.
- Rust action gateway: 34 tests passed, including three direct-model transport/configuration tests; clippy passed with warnings denied.
- Python retirement and policy tests: 32 passed.
- Full Python suite: 1,564 passed, 19 skipped, one unrelated failure. `test_social_icons.py::test_the_changed_stylesheets_are_cache_busted` expects `20261116c`, while website/404.html uses the newer `20261119a`. This is not a clean full-suite pass.
- Disposable local PostgreSQL database: 80 Python/Rust owner HTTP comparisons passed. Existing action settings/state/audit rows survived legacy table renames and two full schema applications. Disposable database removed.
- Known HTTP difference: Hyper normalises trailing Authorization header whitespace; ASGI retains it. This is explicitly tested rather than described as exact parity.
- Mutation check: removing the mandatory PLANNER_MODEL configuration caused the retirement regression test to fail; original source restored.

Remaining Hermes strings in active backend/scripts are intentional legacy-data upgrade identifiers and historical-file exclusion rules. Historical reports retain their original provenance. No runtime dependency remains in the audited source/configuration paths.

The wider Python-to-Rust migration is unfinished: production compose still runs Python; most API routes and background/voice workers remain. The new Rust owner routes are an initial tranche, not a full migration. Rust reporting still uses signed 64-bit aggregate totals; oversized aggregate parity requires resolution before cutover. The retained Rust gateway still calls the Python compatibility API and has an in-memory ledger.
