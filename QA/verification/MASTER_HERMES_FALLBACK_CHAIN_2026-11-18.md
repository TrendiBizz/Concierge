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

## Failover proof (2026-11-18 11:00, agent.log, forced with a nonexistent primary model)
- Claude primary with a bogus model -> `Fallback activated: ... -> gpt-6.1-sol (openai-codex)`, turn answered `HOP2-OK`.
- Codex primary with a bogus model -> `Fallback activated: ... -> grok-4.7 (xai-oauth)`, answered `FAILOVER-OK`.

## Defect found by the failover test
First Claude hop skipped Codex (`Fallback to openai-codex failed: provider not configured`, "no Codex OAuth token found") although `auth status` said logged in. Cause: the Codex pool entry in `auth.json` held stale per-model cooldowns (`model_cooldowns`, from earlier bogus-model probes) and the fallback resolver then found no usable token. Fix: `hermes -p trendi-master auth reset openai-codex` (and `xai-oauth`); the hop then worked. Rule: after probing with fake model names, run `auth reset <provider>`.

## Not verified
UNKNOWN: the Grok -> DeepSeek hop (DeepSeek was tested directly only; Codex sits ahead of it in the chain so it could not be isolated without editing the config).

## Persistence
The profile config lives in the Docker volume `hermes_concierge_data`. `hermes/runtime/apply-fallback.py` (tracked, idempotent, tested on a scratch profile) rewrites the `fallback_model` block, and `start-master.sh` runs it on every start, so a recreate re-applies the chain. The primary (Claude) `model:` block is still volume-only; set with `--provider claude-subscription-directsdk-experimental -m sonnet`.
