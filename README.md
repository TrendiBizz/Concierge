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
Each lead is POSTed to the client's `lead_webhook_url` as
`{"event":"lead.created","tenant":{...},"lead":{name,email,phone,message,channel,page_url,utm}}`.
In n8n, add a *Webhook* node, then e.g. *Telegram/Email* → notify the owner, *Twenty* →
create the contact, *Twilio/Brevo* → text or email the visitor the product link.

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

**Tested here (real components):** unit tests (13 passing); the API against a real PostgreSQL 16 +
pgvector with the real local embedding model; the crawler on a local site (sitemap-less BFS,
`robots.txt` respected); tenant admin, lead capture, stats, origin allow-lists, auth failures;
the widget in headless Chromium (chat, fake microphone, audio capture/playback, tool-call round
trip); `docker compose config` validates with every profile enabled.

**Tested only against mocks:** the LLM (a mock OpenAI-compatible server) and the Grok Voice
WebSocket (a mock). **I had no xAI key, so nothing has run against the real Grok APIs.**

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
