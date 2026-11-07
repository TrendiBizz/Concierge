# What already exists, how SocialSync fits, and whether Hermes should be the integration point

> **DIRECTION UPDATE (Jo, 2026-11-07, later).** Jo rejected re-centring on the separate platform: the CURRENT project stays
> the core, Hermes is the integration layer, SocialSync's core idea is taken into this project, and existing tools are used
> wherever they already do the job. The plan is now `SOCIAL-AND-HERMES-PLAN.md`. Section 2's "platform is the core"
> recommendation and section 5's decisions are superseded. The facts in sections 1, 3 and 4 still stand as reference.

Date: 2026-11-07. Findings from reading (not running) the code on Jo's Mac. Read-only; nothing was changed in those repos.
Claims about the platform come from its own README, HANDOFF and QA report. I have not run any of it.

## 1. The big finding: there is already a Concierge platform

Repo `TrendiBizz/Concierge`, checked out three times in `~/work-staging/` (`concierge-core`, `concierge-integration`,
`concierge-office`, branches `widget-csp-fix`, `integration/concierge-v1`, `office-assistant`). Its README calls it an
"independent, de-bloated alternative to GoHighLevel". Two generations sit side by side:

| Part | What it is (per its own docs) | Status (per its own reports) |
|---|---|---|
| **Core API** (`api/`: FastAPI, Postgres with pgvector, Redis, Caddy) | Website chat and voice widget (Grok Voice in the browser), answers from the customer's own site pages, lead capture, **multi-tenant** (tenant admin, clone), **native booking** with a double-booking guard and server-enforced read-back, an **outbox with retries** (confirmation, 24h and 2h reminders, speed-to-lead text, review request, owner alert emails), **Twilio text with signed two-way inbound** and STOP/START/HELP, SMTP mailer, quote-guard, lead pipeline, admin dashboard, client report, evals | 20 unit tests plus an end-to-end suite passed against real Postgres. **Never run against real Grok, Twilio or SMTP.** |
| **Branch `office-assistant`** | To-dos, sales pipeline, weekly summary, calendar feed | Commit messages only; not inspected |
| **Branch `integration/concierge-v1`** | Signed Cloudflare **inbound email bridge** ("free-first"), release gates | Commit messages only; not inspected |
| **Node modules** (`crm`, `calendars`, `payments`, plus `sites`, `workflows` per README) | Each a small zero-dependency server with its own SQLite and dashboard. Suites pass (11 to 13 tests each). | Payments has **no real payment processing**. |
| **Twenty CRM** (`integrations/twenty`, Docker) plus a **lead bridge** (`POST /lead` on port 4410) | Decision recorded: Twenty is the system of record for the CRM | Bridge verified against a real Twenty (5 of 5 live checks). **The chat widget and calls do not yet feed it.** |
| **SocialSync** (`~/Pukeko/SocialSync`, listed as the "Social" module) | See section 3 | Tests exist; not a git repository |

The platform's own README names its real unsolved problems:
1. **Identity:** every module has its own tenants table and passcode; creating a customer once does not create them elsewhere.
2. **Wiring:** nothing calls module to module (for example a booking does not create a CRM contact).
3. SMS, email, voice and payment providers are stubs or unverified.

## 2. What this means for the plan

My earlier gap analysis (`OFFERING-GAP-ANALYSIS.md`) judged the product by the **voice stack alone**, so it overstated the
gaps. Reminders, two-way text, a CRM, calendars, multi-tenancy and an inbound email bridge exist in the platform. What
is actually missing is **connection and proof**:

| Gap | Real position |
|---|---|
| The phone assistant (this repo, `concierge-stack`, LiveKit and xAI) does not talk to the platform | Nothing connects them. It keeps its own bookings, messages and notifications. |
| Calls and chat do not reach the CRM | Known open item in the platform's own handoff. The lead bridge already exists to receive them. |
| Identity across modules | Unbuilt (platform README calls it the real next step). |
| Real providers | Twilio, SMTP, voice and payments never run for real. |
| A phone line | Not set up anywhere. |

The sensible shape: **the platform is the core** (customers, bookings, outbox, CRM), and **the voice assistant is its
phone channel**, calling the platform's API. The first small, safe step is already built on the other side: give the voice
assistant a CRM adapter that posts each recorded call to the lead bridge. That is the "webhook first" adapter from
`SCALING-AND-INTEGRATIONS.md`, with the platform's own endpoint as its target. The profile design there should reuse the
platform's tenant record (`QA/tenant-concierge.json` and `api/app/tenants.py`), not invent a second one. I have not yet read
those two files.

## 3. SocialSync: what it is and what rolling it in takes

**What it is today.** "SocialSync for Pukeko Construction": plan, check and schedule posts for LinkedIn, Facebook, Instagram
and X. A Node server (no npm packages, built-in SQLite), a web dashboard and a native iPhone app. Compose once, preview per
platform with character counts and platform rules, saved drafts, month calendar, a photo library, a "Due now" list, and
**guardrails** in `server/rules.json` (blocks posts that contradict verified facts or use forbidden wording, warns on
unverified claims and phone calls to action). **It does not publish by itself, by design:** you copy the post or use the
iPhone Share button, then tap "Mark as posted". Its own README says direct publishing "needs an approved developer app per
platform (Meta for Facebook and Instagram, LinkedIn, X) or a posting service such as Ayrshare or Buffer".

**What is customer-specific.** The branding, the verified facts, the forbidden claims, and the single passcode are all
Pukeko's. It is one customer, and it is **not under git** (no history, and not in the backups).

**What the vision needs** ("customers link all their social accounts under Concierge, and we populate the socials"):

| Need | Today | Work |
|---|---|---|
| Many customers | One (Pukeko) | Make brand rules, facts and photos per customer; tenant id shared with the platform |
| Link accounts painlessly | None (manual) | A hosted connect flow. Either a posting service that provides it, or our own OAuth apps per platform |
| Publish automatically | None | The same choice; platform approvals are the slow part (unconfirmed details) |
| Write the posts | Owner writes | Draft from the customer's own website pages (the platform already ingests them) and from Concierge activity, in the customer's tone |
| Safety | Pukeko guardrails | Keep guardrails per customer and **owner approval before anything posts** (a wrong post is public) |

Suggested path: (A) multi-customer SocialSync with AI drafts and an approval step, still manual publish (no approvals needed);
(B) then add publishing through a posting service or our own apps, once Jo picks the route and the cost is known.
Customers would approve drafts from a text or email ("reply YES to post"), keeping it painless.

## 4. Hermes Agent as the integration point

From the project's README and docs (read by a helper; items marked unconfirmed were not read):
- **What:** Nous Research's open-source (MIT) self-improving agent: CLI and desktop app, **MCP client** (stdio and HTTP,
  OAuth), skills, plugins, **a messaging gateway** (Telegram, Slack, WhatsApp, Signal, Email, SMS and more), **a built-in
  cron scheduler**, subagents, six terminal backends including Docker. Very active (multiple releases a week).
- **Headless use:** `hermes gateway` runs as a service; `hermes chat -q` is a one-shot call. An API server with run endpoints
  is named but its auth and exact behaviour are **unconfirmed**. No SDK was confirmed.
- **Multi-customer:** no multi-tenant isolation model is documented. It is built around one owner, with access by allowlist
  and pairing. Separate "profiles" or several gateways on one machine are possible. (Inference; the docs do not say
  "single user".)
- **Risk profile:** it is a general agent with shell and file tools. Safety relies on approval modes and sandboxes (Docker
  recommended); unattended runs deny dangerous commands by default; running with approvals off removes the guard. Its own
  docs say prompt-injection scanning is heuristic.
- **Cost of dependence:** a large, fast-moving project, against the platform's stated rule of having no third-party
  dependency anywhere.

**Assessment.** Hermes is a good fit as **Jo's own operator tool**: draft social posts, run onboarding checklists,
summarise the week, calling Concierge's modules through MCP servers or the existing JSON APIs, inside a Docker sandbox with
a restricted toolset. It is a poor fit as **the production integration layer** that holds customers' data and credentials,
because of the single-owner design, its broad powers, and the maintenance burden. The right integration point for customers
is the small **identity and event hub** the platform's README already says it needs, with the lead bridge, workflow webhooks
and per-customer adapters. If those expose **MCP**, Hermes (or any agent) can plug in later without redesign. Verify
Hermes's API server and multi-profile behaviour before committing to anything more.

## 5. Decisions for Jo

1. **Which is the core?** Recommended: the platform is the core and the voice assistant becomes its phone channel.
2. **SocialSync publishing route:** keep manual publish for now, use a posting service, or build our own platform apps.
3. **Hermes:** operator tool only (recommended), production hub, or skip.
4. SocialSync must go under git and into the backups first (it is in neither today).

## 6. Proposed order once decided

1. Voice assistant CRM adapter to the existing lead bridge (small, testable, no new accounts).
2. Read the platform's tenant record and align the customer profile with it; add the identity hub.
3. Voice assistant reads the customer's knowledge and booking rules from the platform instead of its own env vars.
4. Prove the real providers once (a real text, a real email, a real call) in the platform.
5. SocialSync: git and backups, per-customer rules, AI drafts with approval, then publishing.
6. Reword the website to match what is proven.
