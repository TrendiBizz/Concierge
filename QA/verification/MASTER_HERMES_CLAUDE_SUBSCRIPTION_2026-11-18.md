# Hermes master: Claude subscription provider (2026-11-18)

## Result
Plugin `claude-subscription-directsdk-experimental` v0.3.4 (profile `trendi-master`) drives Sonnet 5.5
on Jo's Claude Max login via the official `claude` CLI 2.1.326. No API key: 0 `ANTHROPIC` entries in
`/opt/data/.env` and the profile `.env`. Live turn: `SONNET-OK` (`-m sonnet --reasoning low`).
`claude auth status`: loggedIn true, authMethod claude.ai, expires 2026-12-16.

## Causes found (two defects)
1. Hermes runs as `hermes` (uid 10000); `claude login` was run via `docker exec` as root, so
   `/opt/data/.claude` and `.claude.json` were root 0600 -> plugin got `Not logged in` (HTTP 401).
   Fix: `chown -R hermes:hermes /opt/data/.claude /opt/data/.claude.json`.
2. Profile HOME is `profiles/trendi-master/home`; plugin setting `claude_config_dir=/opt/data/.claude`
   set, and `.claude.json` copied into that dir (CLI wants it inside CLAUDE_CONFIG_DIR).

## Traps
- `/usr/local/bin/claude` symlink is lost when the container is recreated; CLI stays in `/opt/data/tools`.
  `hermes/runtime/start-master.sh` now recreates the symlink and re-chowns the login on every start.
- Re-login must be followed by the chown (login as root rewrites ownership).

## Use
`hermes -p trendi-master chat --provider claude-subscription-directsdk-experimental -m sonnet --reasoning low`.
Default model unchanged (not switched).

## UNKNOWN
- Whether subscription use via this path is within Anthropic terms.
- Dashboard Models page showing the entry: not checked (dashboard needs a cookie login). Plugin catalog pins Sonnet 5.5.
- Start-script step not run end to end (syntax-checked only).
