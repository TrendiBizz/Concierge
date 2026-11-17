# Hermes default -> OpenAI Codex (ChatGPT plan), 2026-11-18
- Cause: xAI key 403, DeepSeek key 402 ($0, different account). No working default.
- Fix: Jo logged in openai-codex (OAuth). trendi-master config.yaml: default gpt-6.1-sol, provider openai-codex; removed stale xai base_url. Backup: config.yaml.bak-1118 in profile.
- Proof: `hermes -p trendi-master -z "reply with the word ok"` -> ok (gpt-6.1-sol, gpt-5.6-terra both ok). gpt-5/5.5/5-codex rejected on ChatGPT account.
- Open: xAI Grok OAuth login, DeepSeek funded key (optional). Subscription-routing terms UNKNOWN.
