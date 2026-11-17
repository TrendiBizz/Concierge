# Omega Boss routines (exported verbatim 2026-11-18 NZDT; both PAUSED since Jo's 17 Nov 15:01 order)

## Brain weekly health  (id brain-weekly-health)
Schedule: CRON_TZ=Pacific/Auckland 0 9 * * 0 (Sun 09:00, flexible ±15 min)
Calls: /workspace/second_brain/tools/routine-daily.md and routine-weekly.md (copied alongside as routine-daily.md / routine-weekly.md), tools/brain_health.py
Grok-only input: RecallMemory (Grok shared memory). On Hermes, replace with jo-data / Hermes memory or drop.
Saved prompt:
---
Weekly second-brain run (replaces the old daily update too, to save Grok usage). Do it lean: no executor; Grok only gathers what only Grok can read, Claude Code does the writing.
1. Gather the Grok-only input yourself: RecallMemory for shared memory and journal facts from the past 7 days (since the last line in /workspace/second_brain/decisions/). Write them, secrets/emails/phones/addresses stripped, to /workspace/second_brain/.inbox/week.md (create the dir; keep it out of git).
2. In /workspace/second_brain run in one Shell call: `source ~/.claude_oauth_env && claude -p "$(sed '1,/^---8<---$/d' tools/routine-daily.md) EXTRA: the window is the last 7 days, and the Grok memory input is in .inbox/week.md. AFTER that, also do the weekly health job: $(sed '1,/^---8<---$/d' tools/routine-weekly.md)" --dangerously-skip-permissions` (handover compaction included: fold ## Deltas into each bots/handover/*.md body, drop closed items, ≤40 lines, bump updated). Read only its final output lines.
3. Verify cheaply: `python3 tools/brain_health.py --strict` passes and `git log -1 --oneline` shows the push if anything changed.
4. Send Jo one short message: decisions added, health before/after, what was fixed, proposals needing his OK, top 3 TODO(Jo). If Claude Code fails, do it natively and say so.
---

## Friday correction review  (id friday-correction-review)
Schedule: CRON_TZ=Pacific/Auckland 0 16 * * 5 (Fri 16:00, flexible ±15 min)
Grok-only input: ReadTranscript of Grok bot chats. On Hermes, use Hermes session_search / session logs of its own profiles instead.
Saved prompt:
---
Weekly setup-improvement review (Jo's habit 4). Hand to an executor: use ReadTranscript to skim the past 7 days of Jo's chats with Omega Boss, SEO Engine, Trendi Desk, Pukeko and Omega Harness (read only the user turns and the replies around them; don't load full transcripts into context). List every time Jo corrected a bot or had it redo work. For each one, say whether the fix belongs in a skill, a bot's handover/instructions (jo-brain bots/handover/*.md or ~/.claude/CLAUDE.md), or nowhere (a one-off), and write the exact wording to add. Change nothing. Then send Jo a short message that starts with 3 lines (what was found, what he must approve, what's unsure), followed by the list. If there were no corrections, stay quiet.
---

# Box cron jobs run by Omega Boss (claude -p on the box; /workspace/claude-jobs, runner run_job.sh)

## weekly-engine-health
conf:
```
MAX_TURNS=80
TIMEOUT_MIN=120
```
prompt:
```
# Job: weekly-engine-health (Saturdays 09:00 NZ)

Goal: a weekly drift check of every Omega engine's live SHADOW trades against its certified stats.

1. Make the worktree (see rules). Read artifacts/OMEGA_FLOOR.md and the engine config (config/omega_config.ini and the engine init code) to list EVERY engine that is enabled in shadow. Expected to include at least: GBT GAU, ConnorsIBS NAS, NasNy shadow variants, ES-01 gold London-selloff — plus any others the config enables. Report the list and where you got it.
2. Check `ssh omega-new hostname` == fxut8777965. Then pull READ-ONLY copies of the latest shadow trade logs / trade CSVs for each engine from omega-new into @@WORK@@/pull/ (find the log paths from the repo: deploy scripts, the parity harness pull*.py files, or `ssh omega-new "Get-ChildItem ..."` listings). Copy only; never modify anything on the box.
3. For each engine with trades, convert to the CSV format research/tools/quant_checks/cli.py expects (`exit,pnl[,price][,variant][,pnl_stress]`) and run `python3 research/tools/quant_checks/cli.py <csv> --base <variant> --json <out>`. Use price-scaled costs (gold 1.537 bp).
4. Compute for each engine the rolling 3-month window (and all-time shadow): trades, net PF, win rate, max drawdown. Find the certified stats for that engine in the repo artifacts (backtest/, artifacts/, data/exceptional_engines.json, certification docs) and cite the file. Flag drift when the 3-month PF is below the certified PF by more than its stated tolerance, or below 1.0, or the win rate / drawdown is clearly outside certified ranges; say "too few trades to judge" when n < 20.
   Table columns: engine | source of certified stats | certified PF | 3m trades | 3m PF | 3m win% | 3m maxDD | all-time shadow PF | quant_checks verdicts | flag.
5. Do NOT compare with the old MT5 "New York Bull" account — 185 is now the Omega desk; that comparison is dropped.
6. Save the tables as `artifacts/weekly_health/HEALTH_@@DATE@@.md` in the worktree (no raw logs, no secrets), commit, push the branch and open a draft PR.
7. Write the report (rules). NEXT line: FILE = the health file @ the commit sha7; VERDICT = OK / DRIFT: <engines> / NO DATA.
```

## weekly-tools-scout
conf:
```
MAX_TURNS=50
TIMEOUT_MIN=60
```
prompt:
```
# Job: weekly-tools-scout (Mondays 09:00 NZ)

Goal: find at most 5 NEW free/open-source tools, repos or papers that could help Omega.

Omega context: shadow-only engines on gold (XAUUSD) and NAS100 CFDs at BlackBull (MT5 feed), plus IBKR futures relays (GC, NQ, ZN, ES). Interests: sub-second edges, lead-lag between futures and CFDs, order flow / L2, position sizing, cheap or free market data, tick storage/replay (TickArchive), backtest-vs-live parity, DST/clock handling.

1. Make the worktree (see rules). Before searching, collect what has already been assessed: grep the repo artifacts (artifacts/, research/, docs, any SCOUT/EDGE/TOOLS files, previous artifacts/tools_scout/*.md) for repo names, arXiv ids and URLs. Skip anything already there.
2. Search the free web (WebSearch/WebFetch: GitHub, arXiv, Hacker News, Reddit, blogs). Skip anything that is paid per call, closed SaaS, or requires a paid data feed. Prefer things active in the last 12 months.
3. Open every pick's page and verify it exists; record the real URL, licence, last commit/publish date, stars if shown. Never invent a link, repo or paper. If fewer than 5 good picks exist, give fewer (zero is fine).
4. For each pick: what it is, which Omega problem it helps, effort to try, risk, and a concrete first experiment (research-only, shadow-only).
5. Save as `artifacts/tools_scout/SCOUT_@@DATE@@.md`, commit, push the branch, open a draft PR.
6. Write the report (rules). NEXT line: FILE = the scout file @ sha7; VERDICT = N picks / NOTHING NEW.
```

## _common.md (prepended to every box job prompt)
```
# Standing rules for every Omega Claude job (from Jo; these override anything else)
You are running unattended on Jo's box as a scheduled job. Nobody is watching. Work read-only against the trading boxes.

- Never fabricate. Every number, PF, trade count, link or commit you report must come from a file, command output or web page you actually read in this run. If something cannot be measured, write "not measured" and say why.
- All Omega engines are in SHADOW. No agent ever gets an order path. Never place, close, modify or cancel an order. Never touch IBKR / IB Gateway / MT5 order functions.
- Never deploy, build-on-VPS, restart, stop or start Omega or any service/task on any VPS. No writes of any kind on either VPS. Only read-only copies (scp/sftp get, `type`/`Get-Content`, `Get-ChildItem`).
- VPS access is by SSH key only through the alias `omega-new` (LIVE box 185.167.119.59, hostname fxut8777965). Before pulling anything run `ssh omega-new hostname` and continue only if it prints fxut8777965. NEVER connect to 45.85.3.79 / `omega-vps` (RETIRED). Note: `scripts/live_box.tsv` and some pull scripts on origin/main may still name 45.85.3.79 as live (PR #313 fixes this) — ignore them and use `omega-new`.
- Never print or copy secrets: no keys, tokens, TYPESAFE_API_KEY, IBC credentials, passwords. Never run sudo.
- No paid per-call APIs. Free web pages and free public data only.
- Delete nothing in the repo; if you find dead code, list it in the report only.
- DST and clock handling matter: label every time as UTC and NZDT/NZST; use tools/clocks.py where relevant.
- PF goes in markdown tables. Viability bar: pooled net PF from 2020 on, >=100 trades, price-scaled cost at base and 1.5x (gold cost = 1.537 bp of price), must beat the random-entry null. No every-year gate.
- Always read artifacts/OMEGA_FLOOR.md in the repo first.
- Repo: work in a fresh git worktree of Trendiisales/Omegaold made from the clone at /workspace/claude-jobs/repo:
  `cd /workspace/claude-jobs/repo && git fetch -q origin && git worktree add -q @@WORK@@ -b claude-jobs/<job>-@@TS@@ origin/main`
  If you produce repo artifacts, commit them there, `git push -u origin <branch>`, and open a DRAFT PR with `gh pr create --draft -R Trendiisales/Omegaold`. Never merge, never push to main, never force-push. If a push or PR is refused, stop pushing and record the exact error in the report.
- Budget: you have a limited number of turns. Leave enough to write the report.

## Report (mandatory)
Write the final report as markdown to `@@RESULT_FILE@@` (today is @@DATE@@, NZ time). Short and plain: what ran, results (tables for PF/stats), what is flagged, what Jo must decide, the PR link if any.
The very last line of the report must be exactly in this form:
`NEXT: who | FILE: path @ sha7 | VERDICT: … | DEPLOY: NO`
```
