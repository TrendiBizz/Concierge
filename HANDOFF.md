# Handoff - Website AI Concierge (read this first in the new chat)

## Goal
Build a self-hosted "AI concierge for small businesses" business (from a YouTube interview): a chat +
voice widget on a client's website that answers from the site's content, captures leads, books
appointments, and reports results. Voice via **Grok Voice Agent API**. Free/open-source tools
where possible. Sell it on a monthly fee based on lead value, after a free 2-4 week trial and a
live sandbox demo.

## State of play

### Built and tested: `/home/user/concierge`
- `docker-compose.yml`, `Caddyfile`, `.env.example`, `scripts/gen-env.sh`, `scripts/backup.sh`, `postgres/init.sh`, `README.md`
- `api/app/`: FastAPI service (`main, rag, voice, tools, crawler, ingest, chunking, embeddings, llm, tenants, security, db, config, cli`, `schema.sql`)
- `api/static/widget.js`: embeddable chat + Grok voice widget (shadow DOM, AudioWorklet mic capture, tool-call round trip)
- `api/tests/test_units.py`: 20 passing unit tests (run from `api/`: `pytest -q tests`)
- Core services: caddy, postgres+pgvector, redis, api. Optional profiles: n8n, chatwoot, twenty, uptime-kuma.

### Verified for real
Unit tests; the API against real Postgres 16 + pgvector with the real local embedding model
(fastembed bge-small); the crawler (robots.txt respected); tenant admin, lead capture, stats,
origin allow-lists, auth failures; the widget in headless Chromium with a fake microphone;
`docker compose config` validates with all profiles.

### Only tested against mocks
The LLM (mock OpenAI-compatible server) and the Grok Voice WebSocket (mock). **No real xAI key was
used. Nothing has run against real Grok.** The Docker image build and the Chatwoot / Twenty / n8n /
Caddy containers were never booted (no Docker daemon in that environment).

### Assumptions to confirm on the first real run (xAI docs are silent)
1. Which field of the `POST /v1/realtime/client_secrets` response holds the token (`voice.py` accepts `value`, `client_secret.value`, `client_secret`, `token`).
2. Assistant-transcript event names (widget listens for `response.output_audio_transcript.delta` / `response.audio_transcript.delta`) and the interruption event (`input_audio_buffer.speech_started`).
3. The format of the opening "greet the visitor" message (`input_text` content).
4. (Text chat is now Claude - see 'Chat provider' below; only voice uses xAI.)
5. `audio.input.transcription.model = "grok-transcribe"` accepted.
Fixed already: the widget no longer doubles the `xai-client-secret.` prefix.

### Verified xAI facts (from docs.x.ai)
WebSocket `wss://api.x.ai/v1/realtime` (optional `?model=grok-voice-latest`); API key as Bearer header
server-side; browsers use an ephemeral token in the WebSocket subprotocol
`xai-client-secret.<token>`, minted by `POST https://api.x.ai/v1/realtime/client_secrets` with
`{"expires_after":{"seconds":300}}`. Events: `session.update`, `input_audio_buffer.append/commit/clear`,
`conversation.item.create`, `response.create`; server: `response.output_audio.delta`,
`response.function_call_arguments.done`, `response.done`,
`conversation.item.input_audio_transcription.updated`. Parallel tool calls: send ALL
`function_call_output` items before ONE `response.create`. Reported price about $0.05-0.08/min
(sources disagree; confirm at docs.x.ai/docs/pricing).

## SeldonFrame evaluation (done): NOT adopted as base
Cloned (unmodified) at `/home/user/seldonframe/seldonframe` - delete when done. Real project (about
437k lines TS, 756 test files, AGPL-3.0), but: no Grok (phone voice = OpenAI Realtime SIP; chat runtime
= Anthropic SDK); website embed is text-only; solo-maintained, 67 stars, last commit 2026-08-24;
forking it to add Grok triggers AGPL publish obligations; self-host security issues (public
pre-generated secrets in `.env.docker.example`; Postgres HTTP proxy port 4444 published on all
interfaces with default creds); custom domains need Vercel API. Decision: keep our scaffold; borrow
ideas only (quote-guard, enforced booking read-back, scripted evals, event-driven agents).

## DONE in this session: GoHighLevel gap list (Phase 2)
Added and tested (20 unit tests + a 50-check end-to-end suite against real Postgres, plus the
dashboard in headless Chromium): native booking (hours/timezone/slots, `check_availability` /
`book_appointment`, advisory-lock double-booking guard - 6 concurrent bookings of one slot -> exactly
1 wins), **server-enforced read-back** (`conversations.pending_booking`), durable outbox with
retries (confirmation, 24h/2h reminders, speed-to-lead SMS, review request, owner alert emails),
Twilio SMS sender + signature-verified two-way inbound SMS (`/api/v1/sms/{public_key}`) with
STOP/START/HELP and an opt-out table, SMTP mailer, SMS quiet hours (08:00-21:00 local), consent flag,
**quote-guard** (a `$` amount must come from website content / tool results / the client's own text -
visitor-typed amounts do NOT count), lead pipeline (status/notes/value), `/admin-ui` dashboard,
`/report/<token>` client report (no PII), tenant clone (snapshots), `python -m app.evals` (dry run).
New modules: `chat, convo, booking, automation, outbox, events, sms, mailer, contact, guard, evals`;
`main.py`, `tools.py`, `rag.py`, `tenants.py`, `config.py`, `schema.sql`, `widget.js` were changed;
`static/admin.html` is new. README documents all of it.

Test-only mocks live outside the repo (scratchpad): a scriptable mock LLM (`TOOL:{json}`, `SAY:`,
`STUBBORN:` markers), mock Twilio REST, aiosmtpd SMTP, a webhook receiver, and `e2e.py`.
**Not in the zip** - ask to recreate if wanted (or move them into `api/tests/e2e/`).

### Still NOT verified
- Real xAI chat/voice (no key); the 5 voice assumptions listed above.
- Real Twilio and real SMTP delivery; Twilio signature validation only against our own implementation
  (public_base_url must exactly match the URL configured in Twilio).
- `docker build`, and Chatwoot / Twenty / n8n / Caddy containers.
- The eval scenarios against a real model (2 of 6 failed against the dumb mock, as expected).
- Voice replies are not covered by the quote-guard (prompt + `search_knowledge` only).

### Ideas for next steps (none started)
1. First real run with an `XAI_API_KEY`; fix whatever the live API does differently.
2. Move the e2e suite + mocks into `api/tests/e2e/` and add a CI workflow.
3. Missed-call text-back and phone-line voice (Twilio Voice + SIP bridge such as avr-sts-xai).
4. Multi-user logins/roles for the dashboard; per-client custom domains for the widget.
5. Stripe/Invoice Ninja billing; email campaigns; forms/funnels only if clients ask.

## Chat provider: Claude (changed in PR "Use Claude for text chat and SMS")
Text chat, SMS and demo-question generation use the Anthropic Messages API (`api/app/llm.py`,
`api/app/chat.py`). Settings: `ANTHROPIC_API_KEY`, `CHAT_MODEL` (default `claude-opus-5-5`; try
`claude-sonnet-5-5` / `claude-haiku-5-5` to cut cost), `CHAT_EFFORT` (default `low`), `CHAT_MAX_TOKENS`.
Notes: no `temperature`/`top_p`/`top_k` is sent (current Claude models reject non-default values);
tools are passed in Claude's `input_schema` format and all tool results of a turn go back in ONE user
message; the quote-guard retry uses `tool_choice: none`. The old OpenAI-compatible path (xAI text,
LM Studio) was removed. **Voice is unchanged: Grok Voice via `XAI_API_KEY`** (Claude has no realtime voice).
Only tested against a strict mock of `/v1/messages` (unit tests 22 + the 50-check e2e); never against the
real Anthropic API.

## Test environment recipe (if re-creating)
Python venv with `api/requirements-dev.txt`; Postgres 16 + pgvector via apt; fastembed downloads
`BAAI/bge-small-en-v1.5` from Hugging Face on first use (network worked). Env for local API:
`DATABASE_URL=postgresql://postgres@127.0.0.1:55432/concierge ADMIN_TOKEN=... XAI_API_KEY=test
ANTHROPIC_API_KEY=sk-ant-test ANTHROPIC_BASE_URL=<mock> XAI_CLIENT_SECRETS_URL=<mock>/v1/realtime/client_secrets
XAI_REALTIME_URL=ws://127.0.0.1:8097/v1/realtime PUBLIC_BASE_URL=http://127.0.0.1:8000`.
