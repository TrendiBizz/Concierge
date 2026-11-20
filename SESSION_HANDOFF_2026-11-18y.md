# SESSION HANDOFF 2026-11-18y (context-bloat cleanup)

## Git
main @ 0128ce5 (pushed, clean except untracked SESSION_HANDOFF_2026-11-18k/n.md). No repo edits this session; all changes are in ~/.claude.

## Done (all in ~/.claude, backups alongside)
- settings.json: removed retired SessionStart hooks (crypto-desk, wave-companion); cwd-guarded memory-wiki, second-brain, protection, feeds, guards, fxtape hooks to skip in */concierge-integration*. Backup settings.json.bak-2026-11-18b/c/d.
- Plugins disabled globally: all except helper-desk@benai-mods (kept: 1096 calls/30d, provides plan tool).
- MCP removed from ~/.claude.json: codegraph, ghidra, graphify-omega, omega-desk, api-anything, jo-data (configs saved ~/.claude/removed-mcp-2026-11-18.json). Left: ai-memory, desktop-commander. Backup .claude.json.bak-2026-11-18c.
- ~/.claude/skills was emptied by Jo (Finder); synced/ moved to ~/.claude/skills-disabled/synced.

## Traps
- omega-desk removed globally: restore from removed-mcp file before next trading session (desk_status).
- claude.ai connectors (Gmail, Calendar, Drive, Remote Desktop Commander, lseg, finance) not removable from files; Jo must disable in claude.ai settings. Likely biggest remaining startup cost.
- Previous session reported 91% context at thread open (Jo complaint).

## Open ask (next action)
Jo: "check how we stack up when we start a new thread so it doesn't run out of steam immediately". In the new thread: run /context (or read the system-prompt size) right at start, report % used and top contributors (deferred tool list from connectors, CLAUDE.md ~4KB, SessionStart hook output incl. handoff-resume and ai-memory handoff block, UserPromptSubmit hooks). Propose further trims (handoff-resume-sessionstart.sh injects the full previous handoff; ctx-budget-warn hook).
