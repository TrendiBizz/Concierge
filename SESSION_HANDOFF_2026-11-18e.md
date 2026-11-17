# SESSION HANDOFF 2026-11-18e

## Git
main, HEAD 4b399da pushed ("hermes: Claude Sonnet 5.5 via Max subscription plugin..."). Untracked: SESSION_HANDOFF_2026-11-18a/d/e.md.

## Done (verified)
- hermes-concierge: Claude Sonnet 5.5 works via plugin claude-subscription-directsdk-experimental (profile trendi-master). Live turn SONNET-OK; 0 ANTHROPIC in .env. Fixes: chown -R hermes:hermes /opt/data/.claude /opt/data/.claude.json (Hermes runs uid 10000); plugin setting claude_config_dir=/opt/data/.claude; .claude.json copied into .claude/.
- Record: QA/verification/MASTER_HERMES_CLAUDE_SUBSCRIPTION_2026-11-18.md, HANDOFF.md item M12. start-master.sh got symlink+chown step (syntax-checked only).

## Open
- start-master.sh comment cites wrong QA filename (HERMES_CLAUDE_...; real MASTER_HERMES_CLAUDE_...). Edit blocked by hook block-edit-of-running-file.sh false positive (pid 5827 = macOS Virtualization XPC, not the script). Fix later.
- Dashboard (127.0.0.1:9120) Models listing unchecked (cookie login). UNKNOWN: terms of use.

## NEXT (operator ask, not started)
"check if there are any similar cli for openai and grok and install them": i.e. subscription-driven CLI model-provider plugins for Hermes like the Claude one. Look at Hermes plugin list (`hermes plugins list`, hermes-official-plugins repo by NousResearch) for Codex/ChatGPT-subscription (OpenAI Codex CLI) and Grok (xAI; trendi-master default is grok-4.7 provider xai) equivalents. Install in profile trendi-master, login must be done by Jo (never ask for codes in chat; ChatGPT plan / SuperGrok only, NO API billing keys). Remember: run as hermes user (uid 10000), login files must be hermes-owned; CLIs go in /opt/data/tools volume; symlink lost on container recreate. Test with `su -s /bin/sh hermes -c "hermes -p trendi-master chat --provider <id> ... -Q --oneshot -q ..."`. Then QA record, HANDOFF.md, commit, `env -u GIT_CONFIG_COUNT git pull --rebase`, push.

## Traps
No API billing; never print secrets/tokens; env -u GIT_CONFIG_COUNT for git; DeepSeek 402 until Jo tops up; QA/verification/HERMES_* is gitignored (use MASTER_HERMES_ prefix).
