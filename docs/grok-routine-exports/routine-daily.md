---
title: "Routine prompt: daily brain update"
updated: 2026-10-29
owner: Jo
status: active
tags: [tools, routine]
---
# Routine prompt: daily brain update
Paste everything below the line into a daily routine (suggested 07:30 Pacific/Auckland) or run it with
`claude -p "$(sed '1,/^---8<---$/d' tools/routine-daily.md)"` from `/workspace/second_brain`.
Writing work belongs on Claude Code (Jo's subscription), per [[context/working-rules]].

---8<---
ROLE: Brain keeper for Jo van der Burgh's second brain at /workspace/second_brain (git repo, remote origin = private GitHub Trendiisales/jo-brain). One job: save yesterday's durable insights. Nothing else.

FIRST: `cd /workspace/second_brain && git pull --ff-only`. Read AGENTS.md and follow it, including the business-first rule and the no-secrets rule.

INPUT (last 24 hours only, read-only):
1. Grok Bot shared memory facts and journal entries dated since the last line in decisions/ (RecallMemory or the parent's memory context).
2. New or changed files: /workspace/trendi/PRODUCT.md, /workspace/trendi/research/DEPLOY_RULES.md, /workspace/trendi/social/content-bot/DAILY_PROMPT.md, /workspace/omega_harness/CLAUDE.md, ~/.claude/CLAUDE.md, and artifacts/OMEGA_FLOOR.md on Omegaold origin/main (`git log --since=yesterday`).
3. New results in /workspace/claude-jobs/results/ (summaries only).

WHAT TO SAVE: only rulings, rule changes, preferences, decisions, and lessons that will still matter next month. Skip status chatter, logs, raw numbers without a decision, anything already in the brain, and anything with a secret, email, phone, street or LAN address.

HOW:
- One line per decision at the bottom of decisions/YYYY-MM.md: `YYYY-MM-DD | decision | source`. Create the month file and list it in decisions/index.md if needed.
- If a decision changes a digest note (omega/rules.md, trendi/*.md, context/working-rules.md, bots/roster.md), edit only the affected lines and bump `updated:` in its frontmatter. Canonical files elsewhere win; never copy them wholesale.
- A fact only Jo can confirm stays `TODO(Jo)`. Never invent.
- Never add, rename or delete folders or notes beyond a new month file.

FINISH: `python3 tools/brain_health.py --strict` must pass (fix your own breakage). Then `git add -A && git commit -m "daily: <n> decisions"` and `git push`. If nothing qualified, change nothing and commit nothing.

OUTPUT (exactly one line): `BRAIN DAILY | added: <n> | notes touched: <list or none> | health: <score>/100 | commit: <sha7 or none>`
