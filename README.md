# Website AI Concierge - self-hosted stack

Put an AI chat + Grok voice assistant on a small business's website. It answers from the
site's own content, captures leads, books appointments, and reports results per client.

```
Visitor's browser                      Your server (docker compose)
┌──────────────────┐   text chat   ┌───────────────────────────────────────────┐
│  widget.js       │ ────────────► │ api (FastAPI)                             │
│  (1 script tag)  │               │  ├ RAG: crawl → chunk → embed (local) →   │
│                  │  token        │  │       pgvector search                   │
│                  │ ────────────► │  ├ chat LLM (Grok, OpenAI-compatible)     │
│                  │               │  ├ mints short-lived Grok Voice tokens    │
│                  │  voice (WS)   │  ├ tools: capture_lead / booking / search │
│                  │ ──► api.x.ai  │  └ lead webhook ─► n8n ─► CRM / SMS / email│
└──────────────────┘               │ postgres+pgvector · redis · caddy (TLS)   │
                                   │ optional: n8n · Chatwoot · Twenty · Kuma  │
                                   └───────────────────────────────────────────┘
```

Voice audio goes browser → xAI directly (low latency). Your long-lived `XAI_API_KEY` never
reaches the browser; the widget only gets a 5-minute token. Tools run on your server and are
scoped to the client that owns the widget key.

## Quick start

```bash
cd concierge
./scripts/gen-env.sh            # creates .env with random secrets
nano .env                       # set XAI_API_KEY (and DOMAIN for production)
docker compose up -d --build    # core: caddy, postgres, redis, api
docker compose logs -f api
```

Enable optional services by editing `COMPOSE_PROFILES` in `.env`
(`automation` = n8n, `support` = Chatwoot, `crm` = Twenty, `ops` = Uptime Kuma).
Chatwoot + Twenty together want ~8 GB RAM; core + n8n runs fine on 2-4 GB.

The API is also on `http://127.0.0.1:8000` for local use. For a real domain, point
`api.`, `n8n.`, `crm.`, `chat.`, `status.` A-records at the server and set `DOMAIN` and
`PUBLIC_BASE_URL=https://api.yourdomain.com`; Caddy gets TLS certificates automatically.

## Winning a client (the workflow from the interview)

```bash
# 1. Build the sandbox demo for a prospect (about 1 minute)
docker compose exec api python -m app.cli demo \
    --name "Acme Forklifts" --url https://acmeforklifts.example \
    --incentive "10% off when you book online"
```

It prints a demo URL (`/demo/<slug>?presenter=1`) and **five test questions** tailored to that
business. Open the demo on your laptop (or print the URL) and ask those questions live.

```bash
ADMIN=http://127.0.0.1:8000;  H="X-Admin-Token: $(grep ^ADMIN_TOKEN .env | cut -d= -f2)"

# 2. Fill gaps in the knowledge base (price lists, FAQs - survives re-crawls)
curl -X POST $ADMIN/admin/tenants/acme-forklifts/ingest-text -H "$H" -H 'Content-Type: application/json' \
     -d '{"label":"price-list","title":"Price list","text":"New 6000 lb electric: $34,500 ..."}'

# 3. Configure the client (booking link, where leads go, which domains may use the widget)
curl -X PATCH $ADMIN/admin/tenants/acme-forklifts -H "$H" -H 'Content-Type: application/json' \
     -d '{"booking_url":"https://cal.com/acme/visit","lead_webhook_url":"https://n8n.yourdomain.com/webhook/acme-leads","allowed_origins":["https://acmeforklifts.example"]}'

# 4. Go live: give the client the one-line snippet from the tenant record
curl $ADMIN/admin/tenants/acme-forklifts -H "$H"      # -> embed_snippet

# 5. Weekly: results and transcripts (use them to improve the knowledge base)
curl "$ADMIN/admin/tenants/acme-forklifts/stats?days=30"          -H "$H"
curl  $ADMIN/admin/tenants/acme-forklifts/leads                    -H "$H"
curl  $ADMIN/admin/tenants/acme-forklifts/conversations            -H "$H"
```

Other admin endpoints: `GET/POST /admin/tenants`, `PATCH/DELETE /admin/tenants/{slug}`,
`POST /admin/tenants/{slug}/crawl`, `POST /admin/tenants/{slug}/demo-questions`.
Interactive docs: `/docs` (FastAPI).

### Lead routing with n8n
Events are POSTed to the client's `lead_webhook_url`:
`lead.created` -> `{"event","tenant","lead":{name,email,phone,message,channel,page_url,utm}}`;
`appointment.booked | completed | cancelled | no_show` -> `{"event","tenant","appointment":{...}}`.
In n8n, add a *Webhook* node, then e.g. *Telegram/Email* → notify the owner, *Twenty* →
create the contact, *Twilio/Brevo* → text or email the visitor the product link.

## Using a local model with LM Studio (free text chat)

LM Studio can replace the paid text model. **Voice still needs an xAI key** (Grok Voice has no local
equivalent here), and a laptop-hosted model is not reachable from a remote server - this is for running
the whole stack on your own Mac.

On the Mac, from the repo folder (needs Docker Desktop and LM Studio with its `lms` CLI):

```bash
git pull
./scripts/configure-lmstudio.sh        # lists your models, asks which one, writes .env
./scripts/start-concierge.sh           # LM Studio server -> load model -> docker compose up
```

- Double-click **Start Concierge.command** / **Stop Concierge.command** in Finder instead, if you prefer.
- **Start at every login:** `./scripts/install-autostart-macos.sh` (remove with `--uninstall`; log at
  `~/Library/Logs/concierge-start.log`). Also tick "Start Docker Desktop when you sign in" in Docker Desktop.
- The start script is idempotent: a running server or an already-loaded model is left alone.
- Pick a model that supports **tool calling** (recent Qwen / Llama instruct models); otherwise booking and
  lead capture will not trigger. Quote-guard and the booking read-back catch some, not all, small-model mistakes.
- If you enabled authentication in LM Studio, put its token in `.env` as `LLM_API_KEY`.
- Tested with stand-in `lms` / `docker` / `launchctl` commands, not with a real LM Studio install: the exact
  `lms` flags can differ by version (check `lms load --help`), so the first run on a real Mac may need a tweak.

## GoHighLevel-style features (added)

| Feature | How it works | Needs |
|---|---|---|
| **Native booking** | Per-client business hours, timezone, slot length and notice rules. The AI calls `check_availability` and `book_appointment`; times come only from the server. Bookings are serialised per client, so two visitors can never take one slot. | `native_booking: true` |
| **Enforced read-back** | `book_appointment` never books on the first call; it returns a sentence to read back, and only a second call with `confirmed=true` for the *same* time and name (stored in the database) creates the booking. | - |
| **Reminders & follow-ups** | Durable outbox with retries: booking confirmation, reminders 24h and 2h before, speed-to-lead text, review request 1h after a visit is marked completed. Texts are held outside 08:00-21:00 local time. | Twilio and/or SMTP |
| **Two-way SMS** | Point the client's Twilio number's *inbound SMS webhook* at `sms_webhook_url` (shown in the dashboard / tenant record). Signature-verified; the AI replies by text using the same brain. STOP / START / HELP are handled. | Twilio |
| **Opt-outs & consent** | The AI asks permission; `consent_to_contact` is stored; STOP is honoured for every later message. SMS only goes to numbers that consented (or texted first). | - |
| **Quote-guard** | A reply may contain a `$` amount only if it appears in the website content, a tool result or the client's own text. Otherwise it is regenerated, then replaced with a safe fallback. Counted in stats. **Text/SMS only - spoken voice replies cannot be intercepted.** | - |
| **Lead pipeline** | Status (new / contacted / booked / won / lost), notes and deal value per lead. | - |
| **Owner alerts** | Email to `notify_email` on every lead and booking. | SMTP |
| **Dashboard** | `/admin-ui` - overview, leads (edit status/value), appointments, conversations (guard saves highlighted), outbox, settings. Token stays in the tab's session storage. | `ADMIN_TOKEN` |
| **Client report** | `/report/<report_token>` - read-only page for the client: conversations, leads, appointments, estimated pipeline, chart. No contact details. Share the link from the tenant record. | `lead_value_cents` |
| **Snapshots** | `POST /admin/tenants/{slug}/clone` copies settings (persona, hours, SMS template...) to a new client; not knowledge, contacts or keys. | - |
| **Evals** | `python -m app.evals --slug acme` replays tricky scenarios (invented prices, "are you human?", prompt injection, lead before contact, booking without read-back) in dry-run mode and grades them with code. | working LLM key |

Quick setup for a client:
```bash
curl -X PATCH $ADMIN/admin/tenants/acme -H "$H" -H 'Content-Type: application/json' -d '{
  "native_booking": true, "timezone": "America/Chicago",
  "business_hours": {"mon":[["08:00","17:00"]],"tue":[["08:00","17:00"]],"wed":[["08:00","17:00"]],"thu":[["08:00","17:00"]],"fri":[["08:00","17:00"]],"sat":[],"sun":[]},
  "slot_minutes": 30, "sms_enabled": true, "notify_email": "owner@acme.com",
  "review_url": "https://g.page/r/xxxx", "lead_value_cents": 250000 }'
```

**Not built (deliberately):** funnel/landing-page builder, invoices and Text2Pay, social planner,
memberships, courses, affiliates, ads manager, mobile app, multi-user logins/roles, per-client custom
domains, missed-call text-back and real phone-line voice (needs Twilio Voice plus a SIP bridge).

## Free / open-source components (and what to check)

| Need | Tool | Cost | Licence (from memory - **verify before reselling**) |
|---|---|---|---|
| API + widget | this repo (FastAPI, vanilla JS) | free | yours |
| Vector DB | Postgres + pgvector | free | PostgreSQL licence |
| Embeddings | fastembed + `bge-small-en-v1.5` (local CPU) | free | Apache-2.0 / MIT |
| Page text extraction | trafilatura | free | Apache-2.0 |
| TLS / reverse proxy | Caddy | free | Apache-2.0 |
| Workflow automation | n8n | free self-host | **Sustainable Use licence** - fine for running your own/clients' automations, not for reselling n8n itself. Activepieces (MIT) is the swap-in. |
| CRM | Twenty | free self-host | AGPL-3.0 - fine for internal use; modifying + offering it as a service obliges you to publish changes |
| Human inbox / handoff | Chatwoot | free self-host | MIT core |
| Uptime alerts | Uptime Kuma | free | MIT |
| Booking | Cal.com **cloud free tier** | free | Self-hosting Cal.com is heavy; not included |
| LLM + voice | xAI Grok | **paid, usage-based** | see below |

## Add-ons you still need (not in the compose file)

1. **Outbound SMS / phone numbers** - no free option exists. Twilio or Telnyx (pay per message). Wire through n8n.
   Voice over a real phone line (not just the website) would need a SIP bridge, e.g.
   [avr-sts-xai](https://github.com/agentvoiceresponse/avr-sts-xai) - not built here.
2. **Transactional email** - Brevo (free tier ~300/day), Resend, or any SMTP. Chatwoot also needs SMTP for invitations/notifications.
3. **A server** - any 2-8 GB VPS (Hetzner, DigitalOcean, etc.), a domain, and Cloudflare DNS (free).
4. **Backups** - `scripts/backup.sh` dumps every database nightly (add to cron); copy `backups/` offsite with rclone (Backblaze B2 / S3 / Drive). Test a restore once.
5. **JavaScript-heavy or bot-blocked client sites** - the built-in crawler reads server-rendered HTML and obeys `robots.txt`.
   For SPAs add a headless-browser crawler (Crawl4AI / Playwright), or paste content with `ingest-text`.
   Only index sites you own or have the owner's permission to index.
6. **Client reporting** - `/stats` gives conversations, leads and daily series. For dashboards, point Metabase (AGPL) at the `concierge` database.
7. **Traffic baseline for pricing** - ask the client for Google Analytics / Search Console access (free). DataForSEO or SEMrush are paid estimates.
8. **Abuse protection** - per-IP/session rate limits and a per-client daily voice cap (`voice_daily_limit`) are built in. For public sites also add Cloudflare Turnstile (free) in front of the token endpoint.
9. **Billing** - Stripe (fees apply) or Invoice Ninja (free self-host) for monthly invoices.
10. **Error tracking / LLM tracing** (optional) - GlitchTip or Sentry free tier; Langfuse for prompt traces.

## Compliance - do not skip

- **Say it is an AI.** The widget footer and the prompts do this. Do not clone a real person's voice without their written consent, and keep the "AI guide" label even if you do.
- **Recording notice.** Conversations and voice transcripts are stored; the widget says so. Add a privacy policy on the client's site covering AI chat, transcripts and data retention, and honour deletion requests (`DELETE /admin/tenants/{slug}` removes a client's data; individual leads can be deleted in SQL).
- **Texting and calling visitors** needs consent (US: TCPA; EU/UK: GDPR/PECR). The agent only collects contact details a visitor volunteers - get explicit consent wording reviewed before automating outbound follow-up.

## Costs (rough, verify current pricing)
Grok Voice is reported at about **$0.05-0.08 per minute** plus tool calls (third-party sources
disagree; confirm at docs.x.ai). Text chat is billed per token. Embeddings, hosting software and
the CRM/automation stack are free; you pay for the server, SMS, and LLM usage.

## What is verified vs not

**Tested here (real components):** unit tests (20 passing); a 50-check end-to-end suite against real Postgres (booking, read-back enforcement, 6-way concurrent double-booking race, SMS/email outbox, opt-out, quiet hours, signature-verified inbound SMS, quote-guard, pipeline, clone, report, dashboard); the admin dashboard in headless Chromium;  the API against a real PostgreSQL 16 +
pgvector with the real local embedding model; the crawler on a local site (sitemap-less BFS,
`robots.txt` respected); tenant admin, lead capture, stats, origin allow-lists, auth failures;
the widget in headless Chromium (chat, fake microphone, audio capture/playback, tool-call round
trip); `docker compose config` validates with every profile enabled.

**Tested only against mocks:** the LLM (a mock OpenAI-compatible server), the Grok Voice
WebSocket, **Twilio** (a mock REST endpoint) and **SMTP** (a local test server). The eval scenarios were run against the mock LLM, so two correctly failed; they have never been run against a real model. **I had no xAI key, so nothing has run against the real Grok APIs.**

**Not tested:** `docker build` of the API image, and booting the Chatwoot / Twenty / n8n / Caddy
containers (no Docker daemon in my environment). Chatwoot and Twenty settings follow their
documented compose layouts but those projects change often - if one fails to start, compare
with its current official `docker-compose.yml`.

**Assumptions to confirm on first real run** (xAI's docs leave these unstated):
1. The `client_secrets` response field holding the token (`voice.py` accepts `value`,
   `client_secret.value`, `client_secret` or `token`, and logs the keys if none match).
2. The assistant-transcript event names (the widget listens for `response.output_audio_transcript.delta`
   and `response.audio_transcript.delta`) and the visitor-interruption event
   (`input_audio_buffer.speech_started`). If transcripts do not appear in the chat panel or logs,
   check browser console / the actual event names and adjust `onServerEvent` in `static/widget.js`.
3. The format of the opening "greet the visitor" message (`input_text` content type).
4. `CHAT_MODEL` default `grok-4` - set it to a model name your xAI account actually has.
5. `audio.input.transcription.model = "grok-transcribe"` (from the docs) is accepted for your account.

## Layout

```
docker-compose.yml  Caddyfile  .env.example
postgres/init.sh              creates the 4 databases + pgvector
scripts/gen-env.sh            random secrets  |  scripts/backup.sh  nightly dumps
api/app/                      FastAPI service (main, rag, voice, tools, crawler, ingest, cli)
api/static/widget.js          the embeddable widget (chat + Grok voice)
api/tests/                    unit tests (cd api && pip install -r requirements-dev.txt && pytest)
```
