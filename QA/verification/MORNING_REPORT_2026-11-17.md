# Morning report — 2026-11-17

## What was asked

Jo: every morning there should be one written report covering Omega (status, how many
trades, what they were) and Concierge (what was built, fixed or deployed), plus what the
SEO engine did.

The existing 08:00 `master-daily-brief` did not do this. It merged only the Hermes lane
reports (SEO, desk, pen-test, site-watch, workwatch) and explicitly treated Omega as a
different project. It also had no Concierge build/deploy section.

## What was built

- `scripts/reports/morning_brief.py` — deterministic collector and report writer.
  - Omega: SSH `omega-new`, reads `C:\Omega\logs\health\status.json`,
    `omega_config.ini` mode line, and `logs/trades/omega_trade_closes.csv`. Reports
    live vs shadow separately, open positions, build hash, FAIL/WARN checks, and each
    closed trade in the window.
  - Concierge: `git log` for the window (code/config commits grouped by area; handoffs
    counted, not listed), `scripts/vps/verify-deploy.sh`, and the deployed health check
    (46 ok / 2 warn / 0 fail).
  - Lanes: reads `~/.workwatch/reports/hermes/<lane>/latest.md`; a missing lane is
    `UNANSWERED`, never quiet.
  - Every number carries its source. A failed source is `UNANSWERED`, not guessed.
- `scripts/install-morning-brief-macos.sh` — installs the macOS LaunchAgent
  `com.trendi.morning-brief`, daily at 07:45, writing
  `~/.workwatch/reports/hermes/trendi-master/morning-<date>.md` and `morning-latest.md`.

## Live proof (2026-11-17 21:44 NZDT)

- `launchctl print gui/$(id -u)/com.trendi.morning-brief`: loaded, one test run,
  `last exit code = 0`.
- Report written: `~/.workwatch/reports/hermes/trendi-master/morning-latest.md`
  (3437 bytes), and the dated copy.
- Omega at that run: service `WARN`; mode `SHADOW`; 0 broker positions; 0 live trades
  and 4 shadow trades in 24h (net shadow -$13.46); last live trade 2026-10-16. The
  retired IBKR gateway check is excluded; disk 14 GB is a WARN.
- Concierge: `repo and box agree` at `7dfae37`; health 46 ok / 2 warn / 0 fail
  (`inbound:onboarding`, `sms:inbound`).
- SEO: `quiet` (monitor run 14:48, 62.6s); `trendi-desk` and `pen-test` had no report.

## Open

- The report is not yet posted into Hermes Chat. It is written to the mounted reports
  tree, which the dashboard's Files page can read. A no-agent Hermes job could `cat` it
  at 08:00, but `bot-chat` delivery wakes the bot; that needs a deliberate choice.
- The 08:00 `master-daily-brief` still writes its own narrow `latest.md`. The new report
  is `morning-latest.md`, so the two do not overwrite each other. Decide whether the
  master brief should consume the morning report and stop duplicating the lane table.
- Omega is in SHADOW and has not traded live since 2026-10-16. That is a desk decision,
  not a reporting defect; the report now surfaces it every morning.
