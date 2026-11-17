# Hermes master: subscription-first fallback chain (2026-11-18)

Ask (operator): when Claude stops switch to Codex, when Codex stops switch to Grok, when Grok stops use the DeepSeek API. No API billing except DeepSeek as the last step.

## Cause
Default was Codex only, with no ordered fallback; DeepSeek has no subscription/CLI route (catalog searched; `dsh` is an API harness), so the API key is the last resort only.

## Config (profile `trendi-master`, `/opt/data/profiles/trendi-master/config.yaml`, hermes-owned)
Primary: Claude Sonnet via `claude-subscription-directsdk-experimental`. Then:
```yaml
fallback_model:
  - provider: openai-codex
    model: gpt-6.1-sol
  - provider: xai-oauth
    model: grok-4.7
  - provider: deepseek
    model: deepseek-v4-flash
```
Backup of the previous file: `config.yaml.bak-pre-chain` (in the profile dir).

## Proof (FACT, container `hermes-concierge`)
- `hermes -p trendi-master fallback list` shows the 3 entries in that order.
- Plain turn answered `CHAIN-OK` via Claude (primary).
- `auth status xai-oauth`: logged in (SuperGrok device login approved by Jo, credential `xai-oauth-oauth-1`).
- `chat --provider xai-oauth -m grok-4.7 -Q -q "reply GROK-OK"` returned `GROK-OK`.
- Codex logged in (ChatGPT plan); DeepSeek credential "Hermes" answered `DS-OK`.

## Not verified
UNKNOWN: the automatic hop on a real primary failure (each provider was tested directly, not by forcing a failover).

## Persistence
The file lives in the Docker volume `hermes_concierge_data`, not in this repo. `hermes/runtime/start-master.sh` only rewrites `/opt/data/config.yaml` (the root default), so a restart or container recreate keeps the profile config; losing the volume loses it. Re-apply from the block above.
