# SESSION HANDOFF 2026-11-18a

## Git
- main, HEAD 8bac2bf (hermes: default to DeepSeek flash, keep DeepSeek key across restarts), pushed.

## Done this session
- Cause of Hermes errors: xAI/Grok API 403 (team credits exhausted) plus wrong grok model setting. Grok app 4% is a separate meter.
- Live container hermes-concierge: /opt/data/config.yaml and all profile configs set to deepseek-v4-flash / provider deepseek. Operator then fixed the Grok setting in the dashboard (Models page, profile trendi-master still showed xai grok-4.7 at 09:46).
- hermes/runtime/start-master.sh: default model deepseek-v4-flash, provider deepseek, DeepSeek key preserved when .env is rewritten.
- DeepSeek test call returned HTTP 402 Insufficient Balance: operator must top up https://platform.deepseek.com/top_up.

## NEXT ACTION (operator ask, not started)
Add "Claude Sonnet 5.5, low effort" as a selectable model in the Hermes dashboard (http://127.0.0.1:9120, Models page). Check `docker exec hermes-concierge hermes model` / `hermes fallback` and the config for an anthropic provider; no Anthropic API billing is allowed (Claude Max only), so if Hermes needs an API key, STOP and tell Jo rather than adding one. Never print secrets.

## Open
- DeepSeek credit top-up (Jo).
- LinkedIn weekly poster: Jo must log in once via ./scripts/social/linkedin-login.sh and say "logged in"; then dry test.
- LinkedIn first comment (trendibizz.com/concierge) not added.
- Press follow-ups 24 Nov; Search Engine Journal form unsent (Turnstile).
- Handoff 17g contents not re-verified.

## Traps
- Session was repeatedly stopped by a cyber safety classifier on Sonnet 5.5; keep requests narrow.
- Use `env -u GIT_CONFIG_COUNT git ...`. Run verify-deploy.sh before claiming any deploy.
