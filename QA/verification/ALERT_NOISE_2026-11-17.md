# Alert email noise — 2026-11-17

Cause: `healthcheck.py` re-mailed a still-bad check every 6 h (`HEALTH_REMIND_HOURS=6`); a warning that
blinked off and on (`inbound:onboarding`, tenant `trendibizz`) mailed "new" then "recovered" on every swing;
`alert.sh` sent a second "ALERT:" mail at most hourly for any failing run.

Fix: reminder default 48 h; a warning that clears is silent, and one that returns inside the window is not
re-announced; `alert.sh` quiet period 172800 s. Failure recoveries are still mailed.

Proof: 4 tests in `api/tests/test_healthcheck_notifications.py`. Mutation (default back to 6) -> 2 red, restored.
Suite 1478 passed, 29 failed (the known local-Postgres failures).

Not changed: the `trendibizz` tenant is still missing `owner_account`/`consent`, so that warning stays in the
report; it now mails once and reminds every 2 days.
