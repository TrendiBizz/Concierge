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
- `api/tests/test_units.py`: 13 passing unit tests (run from `api/`: `pytest -q tests`)
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
4. `CHAT_MODEL` default `grok-4` - set to a model the account really has.
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

## NEXT TASK (agreed with user, NOT started - no code written for it yet)
"Find all the missing bits GoHighLevel has that we don't, and add them." Research done
(GHL features: CRM + multiple pipelines, calendars with SMS/email reminders, workflows/triggers,
missed-call text-back, reputation/review requests, forms + funnels, email marketing, invoices /
Text2Pay, social planner, snapshots, client portal, white-label, conversation AI/voice AI).

### Gap analysis and plan
| GHL feature | Status in our stack | Plan |
|---|---|---|
| AI chat + voice | HAVE | - |
| CRM / contacts | partial (leads only) | add lead status/notes/value (pipeline) |
| Calendar + booking | link only (Cal.com) | NEW native booking: business hours, timezone, availability + `check_availability` / `book_appointment` tools, advisory-lock double-booking guard, **server-enforced read-back** (`conversations.pending_booking`) |
| Reminders / follow-up automation | webhook only | NEW outbox + scheduler: 24h and 2h reminders, speed-to-lead SMS, review request after completed visit; retries; sms quiet hours (8am-9pm local) |
| SMS | none | NEW Twilio sender (httpx, no SDK) + inbound two-way SMS webhook (signature validated) running the same chat pipeline + STOP/START/HELP opt-out table |
| Email | none | NEW SMTP sender; owner alerts on lead/appointment |
| Reputation / reviews | none | review request via outbox when appointment marked completed |
| Quote-guard (from SeldonFrame idea) | none | NEW: strip/regenerate replies containing `$` amounts not in context/tool results/user text; flag messages |
| Evals | none | NEW `app/evals.py`: scripted scenarios + deterministic validators (no unknown prices, says it's AI, resists prompt injection, no lead before contact, booking read-back) |
| Snapshots (clone a setup) | none | NEW `POST /admin/tenants/{slug}/clone` (config only, no knowledge) |
| Dashboard | JSON admin only | NEW `/admin-ui` static page (token in sessionStorage) |
| Client portal / reporting | stats JSON | NEW `/report/{report_token}` read-only page (counts, chart, estimated value = leads x `lead_value_cents`; no contact PII) |
| Consent / compliance | notice only | add `consent_to_contact` on lead + booking; honour opt-outs |
| Forms / funnels / landing builder | none | SKIP (client already has a site; widget captures) |
| Invoices / Text2Pay / payments | none | SKIP for now (Stripe / Invoice Ninja externally) |
| Social planner, memberships, courses, affiliates, ads manager, mobile app | none | SKIP (out of scope for a concierge product) |
| Missed-call text-back / real phone calls | none | needs Twilio voice + SIP bridge (e.g. avr-sts-xai); document, don't build yet |
| Multi-user logins / roles | single ADMIN_TOKEN | note as limitation |
| Per-client custom domain | none | note: CNAME the widget host / Caddy on-demand TLS later |

### Design notes already decided
- New tables: `appointments`, `outbox` (dedupe_key unique, claimed_at for crash recovery, FOR UPDATE SKIP LOCKED), `opt_outs`. New columns on `tenants` (timezone, business_hours jsonb, slot_minutes, min_notice_hours, max_days_ahead, native_booking, notify_email, sms_enabled, sms_from, lead_sms_template, review_url, lead_value_cents, report_token), `leads` (status, notes, value_cents, consent_contact, updated_at), `conversations` (pending_booking jsonb), `messages` (flag). Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- Refactor the chat loop out of `main.py` into `chat.run_turn(tenant, session_id, channel, message, ...)` so web chat and SMS share it; raise tool rounds to 4; make `chat_tools(tenant)` / `voice_tools(tenant)` tenant-aware; include current date/time + business hours in prompts.
- Quote-guard cannot intercept spoken voice replies; voice relies on the prompt + `search_knowledge` (document the limitation).
- Test plan: extend the scratchpad mock LLM with `TOOL:{json}` / `SAY:<text>` scripted replies; add a mock Twilio endpoint and `aiosmtpd`; run API against local Postgres (`apt-get install postgresql-16-pgvector`, initdb on port 55432); Playwright for widget/dashboard.
- User preferences: always provide FULL files (no snippets/diffs); never modify core code unless instructed (this task was explicitly instructed); warn at about 70% context with a summary.

## Test environment recipe (if re-creating)
Python venv with `api/requirements-dev.txt`; Postgres 16 + pgvector via apt; fastembed downloads
`BAAI/bge-small-en-v1.5` from Hugging Face on first use (network worked). Env for local API:
`DATABASE_URL=postgresql://postgres@127.0.0.1:55432/concierge ADMIN_TOKEN=... XAI_API_KEY=test
LLM_BASE_URL=<mock>/v1 XAI_CLIENT_SECRETS_URL=<mock>/v1/realtime/client_secrets
XAI_REALTIME_URL=ws://127.0.0.1:8097/v1/realtime PUBLIC_BASE_URL=http://127.0.0.1:8000`.
