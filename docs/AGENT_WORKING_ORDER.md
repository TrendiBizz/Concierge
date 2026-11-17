# Agent working order (Jo's roster of duties, routines, commands, open items)

Supplied verbatim by Jo on 2026-11-17 and again on 2026-11-18. Source of truth for what each Grok Bot
does. The jo-brain copy is read-only from this repo's sessions; if the brain differs, this file shows
what Jo last stated.

## 1. SEO Engine
- **Duties:** runs Trendi's own SEO and AI-visibility cycle for trendibizz.com, and later for each signed client: search-term register, matching terms to pages, crawl fixes, titles, meta descriptions, schema, internal links, sitemap and sameAs. Holds the deploy lock; ships only through the Trendi deploy gate.
- **Doesn't do:** copy or new pages (briefs Trendi Desk), client delivery, accounts and video (Jo's).
- **Routines:** daily site and search monitor 07:30, weekly cycle Mon 08:00, monthly audit 1st 09:00, innovation scout 8th and 22nd 10:00, post brief twice a month.
- **Commands** (in `/workspace/trendi/seo/`): monitoring `monitor/daily_monitor.py`, `monitor/serp_check.py`; audits `audits/crawl.py`, `gsc.py`, `psi.py`, `indexnow.py`; 25-prompt AI panel `ai_panel/run_panel.py`; index coverage `coverage/inspect_sitemap.py`; citations `citations/aggregate.py`; DataForSEO `dataforseo/weekly.py --dry-run` (trial credit only, capped $0.08/week, never topped up); every ship `scripts/seo-gate.sh`.
- **Open items:** index check for the 2-3 Nov pages, llms.txt diff before a new baseline, Concierge meta brief (waiting on Jo), deploy ledger, GSC Removals and Bing Block lists (waiting on Jo).

## 2. Trendi Desk
- **Duties:** client-facing copy and pages from SEO Engine's briefs; social scripts and captions as drafts only; client audits and monthly client reports (drafts); honesty check on everything client-facing.
- **Routines:** trendibizz.com tamper watch daily 07:30, LinkedIn weekly draft Mon 09:00, SEO and pen-test news 1st and 15th 09:00.
- **Commands:** `PRODUCT.md` holds offer facts, briefs go in `staged/`, tamper-watch kit does daily checks. Copy changes ship via a branch Jo's Omega Boss merges and deploys.
- **Open items:** $500 leftovers branch `trendi-desk/seo-500-leftovers-20261117`, VPS known-good baseline, commit the tamper kit after secret scan, WAF / HSTS-preload / worker-redirect follow-ups.

## 3. Workwatch (Grok)
- **Duties:** owns the Workwatch app and SiteWatch (repo Trendiisales/workwatch), daily social drafts on SEO and pen testing, SEO forums deep dive.
- **Routines:** social drafts 07:00, deep dive 07:30, weekly report Mon 08:00 on Jo's Mac.
- **Commands:** `/workspace/workwatch_ops/bin/run_social.sh`, `run_deep_dive.sh`.
- **Open item:** copy the CSP nonce fix into TrendiBizz/Concierge so the next release keeps it.

## 4. Omega Boss
- **Duties:** final say on Omega (Omegaold `CLAUDE.md`, `OMEGA_FLOOR.md`). Accepts or rejects PRs, results and deploy records on origin, settles disputes between bots, merges and deploys Trendi site changes.
- **Also:** Trendi accounts and profiles, video, audit tooling, keeping the brain up to date.
- **Routines:** brain weekly health Sun 09:00, Friday correction review 16:00. Daily Omega trade report runs on Jo's Mac (`com.jo.omega-daily-report`, 08:00), not a Grok routine.
- **Commands:** `scripts/vps/deploy-site.sh` from `~/work-staging/concierge-integration`, then a Cloudflare purge. Box crontab: weekly-engine-health (Sat 09:00), weekly-tools-scout (Mon 09:00).

## 5. Omega Harness
- **Duties:** builds and runs the Omega research harness at `/workspace/omega_harness` (lead, backtest-reviewer, variant-searcher, stats-checker, runtime-monitor agents). Claude Code on Jo's Max plan, commits locally only; one push exception: Trendiisales/jo-data.
- **Routines:** box-restore-guard, box-boot-check.
- **Commands:** `tools/guard.py` blocks the sealed holdout, VPS access and pushes. State in `progress.json`, `features.json`.
- **Next:** F8 (full in-sample grid and stats across rounds), F9 (monitor on pulled VPS copies).

## 6. Pukeko
- **Duties:** marketing plans and drafts for Pukeko Construction in `/workspace/pukeko/`. Never contacts anyone, posts or spends.
- **Status:** waitlisted until Conrad responds; no routines.

## 7. dr eggbot
- **Duties:** designs and creates new Grok Bots from a few preference questions.
- **Routines:** transcript-healthcheck, routine-healthcheck.
- **Scope:** still marked as waiting on Jo in the roster.

## 8. Grok Bot Usage Saver
- **Duties:** weekly review of which bots and routines use the most.
- **Routines:** weekly usage review. Not in the roster yet.

## 9. AI Router Bot
- **Duties:** connected Jo's Claude and ChatGPT plans for Claude Code and Codex. No routines; roster marks it to retire (Jo's call).

## Gaps
- Pen Test bot (kept by Jo on 15 Nov): no written scope, unreachable.
- Omega Canary and Omega Scout: only in the Omega Floor group, no written duties.
