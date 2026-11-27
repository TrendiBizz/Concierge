# OpenAI Realtime telephone provider and A/B harness (2026-11-28)

**Why:** Jo asked which realtime voice is best for answering calls (callers must be able to interrupt cleanly) and
wanted OpenAI available to test against Gemini 3.8 Live, which is what production runs (Grok was removed in a4b7bb6).

**Change (opt-in, default unchanged = `gemini_live`):**
- `api/app/voice_openai.py`: pure protocol pieces (G.711 mu-law codec, `session.update`, tool mapping, header-only auth).
- `api/app/asterisk_bridge.py`: `MediaBridge(provider=...)` with an `openai()` event loop; interruption clears queued audio
  and sends `conversation.item.truncate` with the milliseconds the caller actually heard; transcripts stored caller-first;
  tool results followed by `response.create` after `response.done`; truncate/cancel housekeeping errors not counted.
  `provider_connection()` replaces the inline connect. `register()` uses `phone_voice_ready()` (config.py), also used by
  provider_readiness and owner_onboarding.
- Harness: `api/tests/voice_ab_harness.py` (+ `fake_realtime.py`). `--selftest` is free; `--live ... --yes-spend` costs money.

**Proof:** `test_openai_voice_bridge.py` (18) and `test_voice_ab_harness.py` (6); full suite 2012 passed, 19 skipped.
Mutation checks (each failed the named test): no playback clear on interrupt; wrong truncate milliseconds; no
`response.create` after a tool; benign errors counted; no assistant-transcript deferral. Harness mutation: a provider that
never signals interruption scores a cutoff > 1 s.

**Not verified:** nothing has touched the real OpenAI API (no key yet). Event names follow OpenAI's published GA Realtime
API and are UNVERIFIED until `--live` runs. The Rust shell stays Gemini-only; switching provider requires the dialplan to
point at the Python bridge. No real carrier call, latency numbers or cost per call exist yet.
