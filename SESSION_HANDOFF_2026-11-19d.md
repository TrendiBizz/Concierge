# SESSION HANDOFF 2026-11-19d

## Git
main @ 8c286d8 (local). Unpushed: 138ddea, 2b73d60, 8c286d8. Not deployed. Rules: `env -u GIT_CONFIG_COUNT git`; git pull --rebase, push, then `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. Ask Jo before push/deploy.

## Done this session
- Measured Claude first-turn tokens from transcripts: ~66k before 11-18 cleanup, ~51k after. Bare `claude -p` floor 37.8k; with our config headless 42.4k. Other agents (Codex, DeepSeek, Grok, Hermes, OpenBot) NOT measured.
- ~/.claude: handoff-resume-sessionstart.sh capped ~3KB (.bak-20261119); desktop-commander MCP removed (restore: ~/.claude/removed-mcp-2026-11-19.json); handoff-autowrite.sh now folds only last 8 session notes + 1-line preamble (.bak-20261119, syntax-checked only, not run end to end).
- Repo 8c286d8: AGENTS.md 6.7K->2.5K, HANDOFF.md 47K->5.5K (full text in docs/AGENTS_DETAIL.md, docs/archive/HANDOFF_FULL_2026-11-19.md), scripts/dev/startup-budget.sh (reports LATEST handoff over budget until next auto-write).
- outputs/.session_notes.md trimmed to last 8 lines (full copy in /private/tmp/claude-501/notes-full.md or ~/.claude/handoffs-notes-archive-20261119.md).

## NEXT ACTIONS
1. In this fresh thread: run /context, report first-turn % and compare with 51k.
2. Measure one non-Claude agent's startup tokens.
3. Jo: disable claude.ai connectors (Gmail, Calendar, Drive, Remote Desktop Commander, Claude Docs) in claude.ai settings.
4. Original ask: why `docker` still referenced though VPS is on Podman. Migration COMPLETED 2026-11-17 (QA/verification/PODMAN_MIGRATION_2026-11-17.md, PODMAN_HANDOFF_2026-11-17.md); docker CLI kept as client of Podman socket via /run/docker.sock, so some calls are by design. Grep repo (scripts/vps/*.sh, healthcheck.py, backup-all.sh, watchdog.py, redeploy-api.sh, compose files, systemd, docs) with --exclude-dir=outputs --exclude-dir=QA; classify stale vs intended; fix stale with tests. Read-only ssh to box only.
5. Ask Jo: push the 3 commits?

## Traps
Caveman replies. Jo wants a NEW THREAD at handoff (not continue in a full one). Never print secrets. Never docker compose down -v; never stop trendi/asterisk. Test DB: scripts/dev/test-db.sh first.
