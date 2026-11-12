# Competitor gap analysis — Octovox, GoHighLevel → what Concierge should add

2026-11-12 NZ. Requested by the operator: *"look at similar websites like Octovox and gohighlevel and
tell me what they have that is worth including in Concierge. I do not want bloat, I want genuinely
useful additions."*

Raw evidence, per-feature sourcing and the verified/reported split: `COMPETITORS_RAW_2026-11-12.md`.

Method: primary-source page reads of `octovox.ai` (home, /switchboard, /terms, /about, /partners) and
`gohighlevel.com/pricing` + help centre, then a code-level inventory of what Concierge already has
(`api/app`, `web/portal/src`). Every Concierge claim below was checked against the tree at `9ecbb0c`.
Competitor claims are labelled: **verified** = seen on the vendor's own page; **reported** =
third-party (G2/Capterra/Reddit were bot-blocked, so those are second-hand and affiliate-monetised).

---

## 1. Who these two actually are (this changes the answer)

**Octovox** — [octovox.ai](https://www.octovox.ai/), Octovox Limited, NZ. **Not** an SMB
self-serve receptionist. It is a **SIP overlay sold only through channel partners** — verbatim on
[/partners](https://www.octovox.ai/partners): *"We don't sell direct. You do."* No published
pricing ([/terms](https://www.octovox.ai/terms) §11: fees per order form, *"AI calling minutes may
be charged in addition"*), no trial, no self-serve signup; the CTA is "book a 20-min demo". Zero
independent review footprint. Verticals include **construction** and healthcare — Concierge's market.
Its actual product idea is one thing, and it is a good idea: **the Switchboard console** — a human
supervises several AI calls live, reads transcripts in real time, sees sentiment, and takes over in
one click. Modes: supervised vs autonomous.

**GoHighLevel** — [gohighlevel.com/pricing](https://www.gohighlevel.com/pricing). $97 Starter /
$297 Unlimited / **$497 now branded "Founder"** (verified; help docs still say Agency Pro). 14-day
trial. The tier price is not the cost model — the **wallet** is: LC Email $0.675/1k, workflow
premium steps **$0.01 per execution**, LC Phone at Twilio parity, and Voice/Conversation AI agents
**excluded from the plan** ($50–$97/location or per token). Rebilling with markup is $497-only.
Roughly 30 module families: conversations, pipelines + custom objects, calendars, workflow builder,
funnels, forms, campaigns, reputation, payments/order forms, courses (now "GoKollab"), communities,
reporting, affiliate manager, white-label/SaaS mode, A2P 10DLC Trust Centre, snapshots, API.

**The honest read.** Octovox has no price and no direct motion — it is not a competitor for a
$400/month self-serve product; it is the *reference design for how to make AI answering trustworthy*.
GHL is a competitor on breadth, but its own customers' loudest complaints are **breadth itself**
(learning curve named in 140+ of 651 G2 reviews — *reported*; "settings scattered across three
different menus"; 60–90 days to operational confidence; billing surprises; every module "good enough,
not best in class"). Copying GHL feature-for-feature is exactly the failure mode the operator
ruled out, and the repo's own README already frames Concierge as "a de-bloated alternative to
GoHighLevel". This document keeps that framing and only recommends things Concierge's own customers
would feel inside a week.

---

## 2. Scoreboard — the ten things that actually retain customers in this category

Ranked by the competitor research (telephony reliability and missed-call recovery cause the churn;
funnels and courses do not). "Concierge today" is from the code audit.

| # | Capability | Octovox | GHL | Concierge today | Verdict |
|---|---|---|---|---|---|
| 1 | Calls/SMS/email that actually land | SIP overlay, minutes metered | Twilio parity, LC Email, **deliverability is the #1 complaint** | Brevo relay + DSN/bounces/suppression/audit (just hardened) | **Already better than GHL.** No work. |
| 2 | **Missed-call recovery** (text-back + AI answer) | AI answers instead of missing | **Missed Call Text Back** on all plans | ABSENT. `managed_phone.py` only forwards *unanswered* calls to the AI; nothing texts the caller back | **Build — smallest build, highest ROI** |
| 3 | **Live human supervision / takeover of AI calls** | **The whole product** (Switchboard) | Voice AI + Conversations inbox | PARTIAL: `casetimeline.set_takeover`/`is_paused` for text channels; `phone_calls` transcript only **after** the call (`/owner/phone-calls/{id}/transcript`) | **Build — the differentiator** |
| 4 | Unified inbox: one thread per contact | Switchboard + CRM | Core (SMS/email/call/voicemail/FB/IG/WA/chat) | PARTIAL: `casetimeline.timeline(tenant, case_key)` already merges channels server-side; Studio shows it only inside Enquiries | **Surface it — nearly free** |
| 5 | Calendar, booking, reminders | Google **+ Microsoft**, multi-calendar | all plans | PRESENT: race-safe `booking.py`, Google OAuth, ICS feed, confirmation + two reminders (`automation.py`) | Done. Microsoft only when a customer asks. |
| 6 | Call → CRM record self-updated | CRM write-back during the call | all plans | PRESENT: `tools._capture_lead`, lead scoring, `sales.py`, Twenty bridge | Done. |
| 7 | Workflow automation, **unmetered** | n/a | Builder is core but **premium steps are metered $0.01/exec** | PARTIAL by design: typed allowlist planner (`hermes_orchestrator.py`), single-shot actions (`automation.py`) | **Keep it narrow. Never meter.** Positioning asset. |
| 8 | Review requests | none advertised | Reputation + Reviews AI | PRESENT: `automation.py:150` on completed appointment with `tenant.review_url` | Done. |
| 9 | **Payments / deposits** | none | Payments, invoicing, order forms | ABSENT. Quotations exist and can be accepted/signed (`quotations.py`, public `/quote/{token}`) but nothing takes money | **Build — quote→money is the hole** |
| 10 | **Dollar attribution reporting** | outcome classification per call | first/last touch, UTM | PARTIAL: `Reports` = counts only; `sales.py` has forecast; quotations carry values | **Build — cheap, renewal-critical** |

Three capabilities GHL charges extra for or shifts onto the customer, where Concierge is already
ahead and should say so in marketing: **human approval before send** (`email_drafts.py` — GHL's
Conversation AI fires autonomously), **consent provenance with an audit trigger**
(`channel_authorization.py` — GHL's A2P 10DLC is "your job"), and **inbound risk/DMARC handling**
(`email_risk.py`, `email_auth.py`). That is the anti-GHL wedge; none of it needs new code.

---

## 3. What is worth adding — six items, ranked by value ÷ effort

Effort is dev-days including tests, at this repo's current test discipline. Nothing here adds a
new module family; each one extends code that already exists.

### A. Missed-call text-back (and "we tried, here's a link") — 2–3 days
**Why.** GHL treats this as a headline feature on every plan because it is the fastest visible win
an owner gets: a missed call becomes a booked job. Concierge already forwards unanswered calls to
the AI, but if the caller hangs up before that — or after hours when the AI is off — the lead is
simply gone. Trendi's own website already sells [missed-call text-back](https://trendibizz.com/missed-call-text-back.html)
as a service (live, verified HTTP 200) while the product has no implementation (audit: ABSENT).

**Build.** On `phone_sip`/Twilio call-ended events: if the call ended with no captured lead and
duration under ~20 s (or `status` in no-answer/busy/failed), queue one SMS through the existing
`outbox` to the caller — booking link + "reply here and we'll pick it up" — and `casetimeline.record`
it as a `phone` enquiry so it lands in Enquiries like any other lead. Rate-limit one per number per
day, honour `opt_outs`, and respect `channel_authorization.is_authorized(tenant, 'sms')`.

**Acceptance.** A synthetic no-answer webhook produces exactly one outbox row, one lead, one
timeline event; second call from the same number inside 24 h produces none; an opted-out number
produces an audit refusal, not a send.

### B. Live call supervision — the Switchboard, narrowed — 4–6 days
**Why.** This is the only thing Octovox has that Concierge does not, and it is the reason an owner
trusts an AI to answer their phone. Octovox's pitch is literally "your staff supervise instead of
answer". Today Concierge's owner sees a transcript *after* the call. That is not supervision.

**What to build (and what not to).** A Studio screen listing calls with `phone_calls.status =
'in_progress'`, showing the live transcript and the caller, auto-refreshing; a **"Take over — call
me"** button that uses the existing `phone_sip.call_control(call_id, action)` to transfer the SIP
call to the owner's number and sets `casetimeline.set_takeover`. **Do not** build live audio
listen-in or AI "whisper" in v1: with Grok SIP the media never touches our server, and forking it
would mean a media server, which is precisely the kind of infrastructure bloat this product exists
to avoid. Text-level supervision + human takeover covers the trust job.

**Why it is cheap here.** The API is already inside the event stream for every SIP call —
`phone_sip.serve_call` receives every `conversation.item.input_audio_transcription.completed` and
`response.output_audio_transcript.done` and writes them with `convo.save_message`. So the data is
already live in the DB; this is a polling/SSE screen plus one button, not new plumbing.

**Acceptance.** A live test call appears in the panel within ~2 s of the first caller turn; pressing
take-over transfers the call and flips the case to paused with an audit row; the panel empties when
the call completes.

### C. One contact timeline everywhere — 2 days
**Why.** This is GHL's real moat (the unified Conversations inbox) and the single biggest
"this feels like a product, not six tools" upgrade. It is 90% built: `casetimeline.timeline()`
already merges email, SMS, chat, phone, quotes, appointments and tasks per `case_key`.

**Build.** Add a Contact/Timeline screen in Studio reading that endpoint with filters, and link every
enquiry, call, quote and booking row into it. Optional 30-line addition that pays for itself:
a per-tenant **"suggest only" mode** for chat/email (AI drafts, owner sends) mirroring GHL's
Autopilot/Suggestive split — `email_drafts.py` already implements exactly this for email, so it is
a flag, not a feature.

**Do not** build a second inbox data model. The backend is done; the work is a view.

### D. After-call intelligence: summary + outcome + next step — 2–3 days
**Why.** Octovox sells "outcome classification" per call because owners will not read transcripts.
Concierge stores transcripts (`conversation.turns`, `voice_records.py`) and already has Grok wired
(`llm.py`) and a task table (`tasks`). One LLM pass per finished call yields: 3-line summary, an
outcome label (`booked` / `quote_requested` / `not_interested` / `wrong_number` / `unresolved`),
a sentiment flag, and — if unresolved — a follow-up task. Surface it in the timeline, the Monday
`weekly_digest`, and the missed-follow-up list.

**Guardrails.** Cheap deterministic pre-checks first (was a lead captured? was an appointment
booked?) and only call the model for the rest; store the label, never re-derive it; cap by
`tenants.voice_daily_limit` which already exists.

### E. Payments on accepted quotations — 3–5 days
**Why.** GHL includes payments/order forms on every plan and it is a genuine switching cost: once
money moves through the tool, nobody leaves. Concierge has the whole quote flow and no way to be
paid — for a construction tenant that is the moment the value is felt. The audit confirms no
checkout, no Stripe route, and `provider_readiness.py:153` only *mentions* a payment link.

**Build (scope discipline).** Stripe Checkout (hosted) only — deposit or full amount on an accepted
`/quote/{token}`, webhook to mark the quotation paid, receipt into the existing `outbox`. **Do not**
build invoices, subscriptions, tax engines or a billing portal; the SEO service is billed separately
by the operator today. That is GHL's bloat trap in miniature.

### F. Attributed revenue, in dollars — 2 days
**Why.** GHL's reporting is its renewal argument, and Concierge's `Reports` screen counts things
instead of pricing them. The data already exists: quotations carry totals and statuses, bookings
carry appointments, leads carry source and channel.

**Build.** One report — "enquiries the AI handled → quotes sent → quotes accepted → value", split by
channel, with the delta against the previous period. Put it on Home. Owners renew on this number.

---

## 4. Deliberately NOT building (the bloat list)

| GHL / Octovox thing | Why not |
|---|---|
| Funnels, website builder, WordPress hosting | Concierge is a receptionist; the tenant already has a site (it is where the widget is embedded). |
| Courses, memberships, communities, "GoKollab" | Unrelated business. Zero overlap with an AI front desk. |
| Affiliate manager, ad manager, SEO/listing resale, prospecting | Operator businesses, not product surfaces. Already sold as services. |
| 30-module dashboard, custom objects, drag-drop workflow palette | The learning curve is GHL's #1 complaint. `hermes_orchestrator.py`'s typed allowlist is a *feature* — keep it. |
| IVR menu trees / call queueing | The AI *is* the menu. Adding trees makes it worse. |
| Marketplace / app directory | One good Twenty bridge beats a directory nobody lists in. |
| Metering automation, AI tokens, or per-minute voice pricing | GHL meters exactly the layer that breeds resentment ("$0.01/execution"). Concierge's flat all-in price is the differentiator — protect it. |
| Live audio listen-in / whisper (v1) | Needs a media server; text-level supervision delivers the same trust. Revisit only if a customer asks. |
| White-label agency hierarchy + SaaS reselling + snapshots | Real money **only if** the operator intends to sell through partners, Octovox-style. Today there is `/admin/tenants/{slug}/clone` and per-tenant branding; that is enough. **Decide the channel question before building it.** |
| A2P 10DLC registration wizard, Microsoft calendar, sentiment-on-live-call | Build on trigger: first US customer; first Microsoft-shop customer; first customer who asks. Not before. |

---

## 5. The one-line strategy this analysis supports

GHL's weakness is that it taxes the customer for the platform — metered automation, metered AI, DIY
compliance, a 60–90 day learning curve — to fund 30 modules they never asked for. Octovox's insight
is that an owner will accept an AI answering the phone **only if a human can watch and take over**.
Concierge should ship: **never miss a call again (A) → the owner can watch and take over (B) → one
timeline (C) → a summary and a next step (D) → the money (E) → the number that proves it (F)**, all
at a flat price, with consent and deliverability already handled. That is a better product than
either, and it is roughly two weeks of work, not two quarters.

Suggested order: **A, C, D** (cheap, visible, compounding), then **B** (the differentiator, needs
a live call test), then **E, F**. A and C alone close the two gaps an owner would notice in a trial.
