---
title: "Routine prompt: weekly brain health"
updated: 2026-11-01
owner: Jo
status: active
tags: [tools, routine]
---
# Routine prompt: weekly brain health
Paste everything below the line into a weekly routine (suggested Sunday 09:00 Pacific/Auckland) or run it with
`claude -p "$(sed '1,/^---8<---$/d' tools/routine-weekly.md)"` from `/workspace/second_brain`.

---8<---
ROLE: Weekly health check and cleanup of Jo van der Burgh's second brain at /workspace/second_brain (git repo, remote origin = private GitHub Trendiisales/jo-brain). One job: keep it lean, correct and routable.

FIRST: `cd /workspace/second_brain && git pull --ff-only`. Read AGENTS.md and follow it.

STEPS:
1. Run `python3 tools/brain_health.py`. Record the score.
2. Fix small things yourself: index.md rows for unlisted files, broken links or wikilinks, missing frontmatter keys, bad `updated` dates, an exact duplicate line, an orphan that belongs in an index.
3. Handover compaction: for each `bots/handover/*.md` (not README, not `profiles-full/`), fold the lines under `## Deltas` into the body (update open items, drop closed ones), then leave `## Deltas` empty. Keep each file at about 30 lines (40 max) and bump `updated`. Never paste transcripts or logs.
4. Review content (read only what you need):
   - Contradictions: the same rule stated differently in two notes, or a digest that disagrees with its canonical file (OMEGA_FLOOR.md on Omegaold origin/main, /workspace/trendi/PRODUCT.md, DAILY_PROMPT.md). The canonical file wins; fix the digest.
   - Stale: notes flagged stale (`updated` over 120 days), or facts superseded by a later line in decisions/.
   - Bloat: any note over ~150 lines or holding raw data instead of insights; AGENTS.md drifting toward 200 lines.
   - Leaks: anything secret-like the checker flags.
5. Do NOT make big changes yourself. Folder changes, deleting or merging notes, rewriting a rule, or resolving a contradiction that needs Jo's judgement go in the report as proposals.
6. Re-run `python3 tools/brain_health.py --strict` (must pass). Commit `weekly: health <score>` and push only if you changed something.

OUTPUT (max 12 lines, no preamble):
`BRAIN WEEKLY | health: <before> -> <after>/100 | fixed: <n> | commit: <sha7 or none>`
Then up to 5 bullets: proposals needing Jo's OK (one line each), then the count of open TODO(Jo) items with the three most valuable to answer next.
