# Hermes master: OpenAI / Grok subscription providers (2026-11-18)

Ask: find CLI-style subscription providers for OpenAI and Grok like the Claude one, install them.

## Finding (FACT, from `hermes plugins list` / `hermes auth status` in hermes-concierge)
- Nothing to install. Both ship bundled and enabled: `openai-codex` (ChatGPT plan, OAuth, base chatgpt.com/backend-api/codex, no API key) and `xai` with an `xai-oauth` login (SuperGrok / Premium+).
- State: `openai-codex` logged out; `xai-oauth` logged out. The existing `xai` credential is an API key (XAI_API_KEY) and returns 403, so it is unusable and is API billing; do not rely on it.

## Operator steps (login must be done by Jo, as the hermes user)
- Codex: `docker exec -it -u hermes hermes-concierge hermes -p trendi-master auth add openai-codex --type oauth`
- Grok: `docker exec -it -u hermes hermes-concierge hermes -p trendi-master model` then pick "xAI Grok OAuth (SuperGrok / Premium+)".
- Login as hermes, not root, so files are hermes-owned (see MASTER_HERMES_CLAUDE_SUBSCRIPTION_2026-11-18.md).
- Then test: `hermes -p trendi-master chat --provider openai-codex ...`.

## Not verified
UNKNOWN: whether either login works end to end; terms of use for subscription routing.
