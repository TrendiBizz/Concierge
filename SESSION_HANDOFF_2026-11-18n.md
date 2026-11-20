# SESSION HANDOFF 2026-11-18n
## Done
- Omega routines go in SEPARATE package: ~/work-staging/omega-hermes (own git repo, 1 commit). Jo chose option 1. Exports moved there from concierge docs/grok-routine-exports/ (verbatim, do not edit). README + draft schedules.yaml (placement + status per routine). Nothing installed/enabled.
- Concierge: docs/grok-routine-exports deletion is UNCOMMITTED in working tree (files were tracked, likely by checkpoint bot). Commit the deletion or restore; Jo's call.
## Next
1. Read exports/omega-harness.md fully (887 lines, scripts incl.) and write routine procedures + profile SOULs (omega-boss, dr-eggbot, usage-saver, omega-harness).
2. Port word for word. Swaps: RecallMemory/ReadTranscript -> Hermes memory/session_search; usage review needs Hermes usage source. dr eggbot skills missing -> DRAFT only. Harness 2 + engine-health need host (omega-new SSH, /workspace/omega_harness), not container.
3. Write installer + manifest test, dry-run, show Jo, --apply only on OK. Grok copies stay paused until Hermes confirmed.
## Still open (Concierge)
FB/IG copy needs 16 Nov LinkedIn source (not found). CSP nonce closed (no drift). Recheck lane_status in container after 19 Nov 07:30 NZDT.
## Traps
No external posting w/o OK; no secrets; no API billing; env -u GIT_CONFIG_COUNT git; caveman mode.

## Operator ask (latest, verbatim): "add the skills from dr eggbot and then complete this task as i asked"
- Task = finish the Omega Hermes port in ~/work-staging/omega-hermes (separate repo, commit 9f5c484): procedures for all 9 routines, profile SOULs, installer, manifest test, dry-run, then --apply only on Jo OK.
- dr eggbot skills "Transcript healthcheck" + "Routine healthcheck" (Grok path /home/box/agent-data/workflows) are NOT on the Mac. Search ~/OpenBot, ~/jo-brain, ~/.grok, ~/.claude for them first. If absent, ask Jo to export the skill text; do NOT invent. Save them as omega-hermes/skills/<name>.md verbatim.
- Concierge repo: docs/grok-routine-exports deletion uncommitted (Jo to decide). Concierge git state: main, last own commit 881038f; checkpoint bot 626af37.
- Do not run box-touching routines from container; host placement per schedules.yaml.
