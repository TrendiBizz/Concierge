# Optional Gemini Live telephone setup

Website voice uses Google Gemini 3.8 Live ephemeral browser tokens (`v1alpha/auth_tokens`).
It does not require `PHONE_RECEPTIONIST_ENABLED` or a DID.
These settings enable ordinary carrier/PBX calls via Asterisk AudioSocket and Gemini 3.8 Live.
A personal owner contact number is a notification target, not proof of a SIP-capable telephone route.

## Server settings

Production loads `/opt/trendi/shared/api.env`, mode `0600`, with Compose raw `env_file`.
Editing `.env.example` does not update runtime settings.

- `PHONE_RECEPTIONIST_ENABLED=true`: opens the global handler; individual businesses
  and phone numbers still require activation and authorization.
- `PHONE_VOICE_PROVIDER=gemini_live`.
- `GEMINI_API_KEY`: Google Gemini API key, server-side only.
- `GEMINI_LIVE_MODEL=models/gemini-3.8-live`.
- `GEMINI_LIVE_VOICE=Aoede` (one of `Aoede`, `Charon`, `Fenrir`, `Kore`, `Puck`, `Leda`, `Orus`, `Zephyr`).
- `GEMINI_THINKING_LEVEL=` (leave blank for `models/gemini-3.8-live`, which rejects `thinkingLevel` with WS `1007`).

## Connect an existing number

Route your carrier SIP trunk (or mobile call forwarding) into the private Asterisk PBX (`asterisk-pbx-1`),
which bridges AudioSocket 8 kHz PCM to `bridge:9510` (`asterisk-bridge-1`, 16 kHz in / 24 kHz out Gemini Live).
See `scripts/asterisk/README.md` for route rendering and dialplan verification.

## Optional: OpenAI Realtime instead of Gemini (Python bridge only)

Set `PHONE_VOICE_PROVIDER=openai_realtime` and `OPENAI_API_KEY` in `/opt/trendi/shared/api.env`, then restart the
bridge. Model, voice and turn detection: `OPENAI_REALTIME_MODEL`, `OPENAI_REALTIME_VOICE`, `OPENAI_TURN_DETECTION`.
- Only the Python bridge (`bridge:9510`) speaks OpenAI. The Rust shell is Gemini-only: keep the dialplan pointing at
  the Python bridge while this provider is selected.
- Website voice (browser tokens) stays on Gemini.
- Compare providers before switching: `python api/tests/voice_ab_harness.py --live openai_realtime gemini_live --yes-spend`
  (costs money; uses macOS `say` for the caller). `--selftest` runs free against fakes.
- Roll back by setting `PHONE_VOICE_PROVIDER=gemini_live`.
