# Full Post-Implementation Audit & Production Deploy — 2026-11-24

## Scope
Integrated, audited, fixed, tested, pushed (`main`), deployed to VPS (`152.42.239.240`, release `20261108-vps`), and verified live:
1. **A2UI sitewide chat cards** (PR #91, `feat/a2ui-sitewide-20261124`) — merged into `main`.
2. **Google Gemini 3.8 Live telephone voice bridge** (`feat/gemini-live-voice-bridge`) — merged into `main` with critical fixes.
3. **GEO daily monitoring fixes** (from `wip/concierge-integration-20261121`: `ff49411` Cloudflare CSP nonce stripping + `60acb52` non-overwriting same-day reports) — cherry-picked onto `main`.
4. **Live production baseline** (`origin/main` `8bea165`, `$199/month` pricing PR #92) — audited and verified.

## Defects Found & Fixed During Audit

### 1. CRITICAL — Gemini 3.8 Live rejected default `thinkingConfig.thinkingLevel="low"` (WS close 1007)
- **Cause:** `feat/gemini-live-voice-bridge` defaulted `gemini_thinking_level` to `"low"` in `api/app/config.py` and `.env.example`, causing `MediaBridge._setup_payload()` to send `generationConfig.thinkingConfig = {"thinkingLevel": "low"}` for `models/gemini-3.8-live`. Probing Google's live `BidiGenerateContent` endpoint proved `models/gemini-3.8-live` immediately terminates the WebSocket with `1007 (invalid frame payload data) Thinking level is not supported for this model.` — which would have failed 100% of live telephone calls.
- **Fix:** Defaulted `gemini_thinking_level` to `""` in `api/app/config.py` and `.env.example` (kept opt-in for extended-thinking models such as `models/gemini-3.8-live-extended-thinking`). Updated `api/tests/test_asterisk_bridge.py` and added `test_setup_payload_omits_thinking_config_by_default_and_includes_when_configured`.
- **Mutation check:** Temporarily reverted `gemini_thinking_level` to `"low"` in `api/app/config.py`; `pytest tests/test_asterisk_bridge.py -k "thinking_config or defaults_and_ws_url"` failed 2/2 as expected; restored to `""` and passed.
- **Live protocol proof:** Verified `MediaBridge._setup_payload()` with all 9 real telephone tools (`voice_tools` + `end_call` + `set_call_recording`) against `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent`: returned `{"setupComplete": {}}`, accepted 16kHz PCM `realtimeInput`, and returned greeting audio (`148,320` bytes 24kHz PCM) + `outputTranscription` + `turnComplete: true`.

### 2. CRITICAL — Live VPS lacked `GEMINI_API_KEY` and Asterisk dialplan still routed calls to the Grok-only Rust shell
- **Cause:** `/opt/trendi/shared/api.env` had no `GEMINI_API_KEY` (and `XAI_API_KEY` was already empty), and `asterisk-pbx-1`'s `extensions.conf` still routed `AudioSocket` to `172.30.91.3:9510` (`trendi-shell-1`, the Rust shell which is still hardcoded to xAI Grok Realtime). Additionally, `scripts/vps/redeploy-api.sh` recreated `trendi-api-1` without recreating `asterisk-bridge-1`, leaving the bridge on stale code/env after deploys; and `scripts/vps/sync-tooling.sh` did not sync `scripts/asterisk/cutover_to_rust_shell.sh`, leaving a pre-Podman `docker` copy on the box.
- **Fix:**
  - Updated `scripts/vps/redeploy-api.sh` to also recreate `asterisk-bridge-1` (`scripts/asterisk/compose.yml`) whenever present.
  - Updated `scripts/vps/sync-tooling.sh` to include `scripts/asterisk/cutover_to_rust_shell.sh` in synced host build/ops files.
  - Provisioned `GEMINI_API_KEY`, `PHONE_VOICE_PROVIDER=gemini_live`, `GEMINI_LIVE_MODEL=models/gemini-3.8-live`, `GEMINI_LIVE_VOICE=Aoede`, and `GEMINI_THINKING_LEVEL=` into `/opt/trendi/shared/api.env` (backup saved at `/opt/trendi/shared/api.env.bak-20261124-gemini-live`, mode `600`).
  - Cut Asterisk `extensions.conf` back from `172.30.91.3:9510` (Rust Grok shell) to `bridge:9510` (`asterisk-bridge-1` at `172.30.91.4`, verified resolvable as `bridge.dns.podman` inside `asterisk-pbx-1`) via `cutover_to_rust_shell.sh --rollback /opt/trendi/backups/rust-shell-cutover-20261120-030829`.

### 3. Operational & Monitoring Improvements
- Added `"trendibizz"` alongside `"trendi-oauth-staging"` in `api/app/a2ui.py` `PRICING_TENANTS` (confirmed live widget key `pk_8y_wsHO4StqCzd0yc2QNEKp0` maps to `trendi-oauth-staging`).
- Added `https://chat.trendibizz.com/a2ui-renderer.js` to `PUBLIC_URLS` in `scripts/vps/healthcheck.py`.
- Updated `scripts/vps/verify-deploy.sh` to print local git branch + short SHA and warn when run from a non-`main` branch.

## Verification Proof
- **Full API test suite:** `scripts/dev/test-db.sh` + `pytest -q` -> **1,958 passed, 42 skipped** (0 failed).
- **Site SEO contract:** `python3 scripts/seo/site_seo.py check` -> `OK: 46 pages — canonical, robots, h1, snippet, dates, links, sitemap and IndexNow key all agree`.
- **Production SEO gate:** `./scripts/seo-gate.sh https://trendibizz.com` -> `PASS=22 FAIL=0 WARN=0` (`GATE RESULT: PASS`).
- **Deploy parity:** `KEY=./Concierge ./scripts/vps/verify-deploy.sh` -> `OK: repo and box agree` (api/app 156, api/static 8, api/migrations 5, scripts/vps 61, website/site 65, API drift guard + live tool smoke OK).
- **Live A2UI endpoints:**
  - `GET https://chat.trendibizz.com/a2ui-renderer.js` -> `HTTP/2 200` (`application/javascript`).
  - `GET https://chat.trendibizz.com/widget.js` -> serves A2UI lazy loader + `/api/v1/chat/action`.
  - `POST https://chat.trendibizz.com/api/v1/chat/action` with `{}` -> `HTTP 422` (FastAPI schema validation live through Caddy).
  - `/404`, `/privacy`, `/security`, `/terms` each serve `https://chat.trendibizz.com/widget.js` (`count=1`).
- **Live phone bridge:** `asterisk-bridge-1` running with `PHONE_VOICE_PROVIDER=gemini_live`, `GEMINI_API_KEY=<SET>`, `GEMINI_LIVE_MODEL=models/gemini-3.8-live`, `GEMINI_THINKING_LEVEL=`, listening on TCP `9510`; Asterisk dialplan points to `bridge:9510` and carrier trunk `concierge-reg` is `Registered`.

## Open Recommendations
1. **Place one real inbound test call** to `+6492431347` (Pukeko Construction) to verify real-world carrier audio quality, barge-in, transcription, and owner alert delivery on Gemini 3.8 Live (synthetic/automated calls are forbidden by repo rules).
2. **Port or retire Rust `trendi-shell-1` (`concierge-stack/core-rs`)**: Currently `trendi-shell-1` still speaks xAI Grok Realtime and requires `XAI_API_KEY` at startup; Asterisk now routes to Python `asterisk-bridge-1` (`bridge:9510`). Either port `core-rs` to Gemini 3.8 Live (keeping it in sync with `asterisk_bridge.py`) or formally retire `trendi-shell-1` from `compose.yml` and `healthcheck.py`.
3. **Website browser voice (`api/app/voice.py`)**: `/opt/trendi/shared/api.env` has `XAI_API_KEY=` (empty). Because browser voice in `widget.js` still mints an xAI ephemeral token (`wss://api.x.ai`), the microphone button on the website widget will return voice unavailable until either `XAI_API_KEY` is populated or browser voice is also migrated to Gemini Live.
4. **Startup budget & stale branches/worktrees**: `outputs/SESSION_HANDOFF_LATEST.md` is 5,120 bytes (over the 4,500-byte budget in `scripts/dev/startup-budget.sh`). Several stale open PRs (#3–#22) and local worktrees (`backup/local-main-20261121`, `wip/concierge-integration-20261121`) can be pruned once reviewed.
5. **A2UI transitive Zod advisory**: Retain release-review tracking for `GHSA-mrhx-c7xc-m3w5` (`@a2ui/lit` -> `zod 3.25.76`); upgrade when upstream `@a2ui/lit` bumps Zod cleanly.
