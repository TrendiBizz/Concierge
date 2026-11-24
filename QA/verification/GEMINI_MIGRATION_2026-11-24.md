# Complete xAI / Grok Removal & Google Gemini 3.8 Live Migration — 2026-11-24

## Scope
Removed all xAI / Grok runtime code across Python API, browser widget, website CSP/privacy policy, host scripts, and Rust telephone shell (`concierge-stack/core-rs`), replacing every voice and default LLM path with Google Gemini protocols, and verified the live USD $199/month Concierge price across website + Stripe checkout.

## Changes
1. **Browser Voice → Google Gemini 3.8 Live (`api/app/voice.py`, `api/static/widget.js`, `api/app/security.py`, `website/_headers`)**
   - Replaced xAI `client_secrets` with single-use Google Gemini Live ephemeral auth tokens (`POST https://generativelanguage.googleapis.com/v1alpha/auth_tokens`, `uses: 1`, `bidiGenerateContentSetup` locked server-side with `models/gemini-3.8-live`, `Aoede` voice, `START_OF_ACTIVITY_INTERRUPTS`, input/output transcription, system instructions, and `functionDeclarations` with `additionalProperties` stripped).
   - Updated `api/static/widget.js` to connect to `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained?access_token=<token>`, decode both text and binary (`ArrayBuffer`/`Blob`) WebSocket frames, resample mic input to 16 kHz PCM16 LE (`realtimeInput.audio`), play 24 kHz PCM16 LE output (`serverContent.modelTurn.parts[].inlineData.data`), handle barge-in (`serverContent.interrupted`), log `inputTranscription`/`outputTranscription`, and round-trip `toolCall` → `/api/v1/tools/<name>` → `toolResponse`.
   - Replaced `wss://api.x.ai` with `wss://generativelanguage.googleapis.com` in `website/_headers` and `api/app/security.py` `DEMO_CSP`.
2. **Removed xAI SIP & Legacy Grok Config (`api/app/phone_sip.py`, `config.py`, `managed_phone.py`, `owner_onboarding.py`, `provider_readiness.py`, `live_calls.py`, `Caddyfile`, `.env.example`, `scripts/`)**
   - Deleted `api/app/phone_sip.py`, `api/tests/test_phone_sip.py`, and `scripts/vps/check-grok-voice.py`; added `scripts/vps/check-gemini-voice.py`.
   - Removed `xai_api_key`, `xai_sip_connections`, `xai_client_secrets_url`, `xai_realtime_url`, `voice_model`, `voice_ws_url`, and `'grok'` from `phone_voice_provider` in `api/app/config.py`.
   - Defaulted OpenAI-compatible text chat fallback to Google Gemini (`https://generativelanguage.googleapis.com/v1beta/openai/`, `gemini-3.8-flash`, `effective_llm_key = llm_api_key or gemini_api_key`); production `/opt/trendi/shared/api.env` keeps its configured `LLM_BASE_URL`/`LLM_API_KEY` for text chat and removes `XAI_API_KEY`/`XAI_SIP_CONNECTIONS`.
   - Updated `api/static/owner.html` and `website/privacy.html` to remove xAI/Grok references.
3. **Rust Telephone Shell → Google Gemini 3.8 Live (`concierge-stack/core-rs/`)**
   - Ported `asterisk_shell.rs`, `media_bridge.rs`, `shell.rs`, `settings.rs`, `voice_session.rs`, `owner_profile.rs`, `telephony.rs`, `tools.rs`, and all Rust tests (`shell.rs`, `parity11.rs`, `parity15.rs`, `parity29.rs`) to Gemini 3.8 Live (8 kHz → 16 kHz upsampling, 24 kHz → 8 kHz downsampling, `GEMINI_API_KEY` / `GEMINI_LIVE_WS_URL`, `setupComplete`, `realtimeInput`, `serverContent`, `toolCall`/`toolResponse`, binary/text WS frame handling).

## Verification Proof
- **Zero runtime xAI/Grok code:** `git grep -niE "xai|grok|api\.x\.ai" -- .env.example api/app/ api/static/ website/ scripts/ concierge-stack/core-rs/src/` returned 0 matches.
- **Live Gemini 3.8 Live checks (`scripts/vps/check-gemini-voice.py`):**
  - Direct WS handshake (`models/gemini-3.8-live`): `OK` (`setupComplete`).
  - Browser ephemeral token minting (`v1alpha/auth_tokens`): `OK` (`auth_tokens/...`) + live `BidiGenerateContentConstrained` session with 16 kHz audio, greeting audio (`78,240` bytes), transcription, and real `search_knowledge` `toolCall` → `toolResponse` → `turnComplete`.
- **Mutation check:** Mutated `uses: 1` → `uses: 99` in `api/app/voice.py`; `test_voice_gemini.py::test_mint_token_mints_single_use_gemini_ephemeral_token` failed red as expected; restored and passed.
- **Rust test suite (`cargo test` in `concierge-stack/core-rs/`):** 0 warnings, 100% passed including `shell_runs_one_call_end_to_end` over Gemini Live protocol.
- **Python full API test suite:** Passed with 0 failures (`api/tests/test_voice_gemini.py` enforces zero xAI/Grok code in `api/app/` and Gemini Live protocol in `widget.js` & CSP).
- **USD $199/month pricing confirmation:**
  - Live Stripe Payment Link `https://buy.stripe.com/eVq28s2qj9jfdxugHm04805`: `active=True`, `unit_amount=19900` (`USD $199.00`), recurring `month`, `Trendi Concierge`.
  - Live `website/products.js`, `https://trendibizz.com/pricing` (`15 × $199`, `0 × $250`), A2UI pricing card (`api/app/a2ui.py`), and `healthcheck.py` `site:prices`: all match USD $199/month.
