# Craft Agents (craft-ai-agents/craft-agents-oss) — what it would actually do for us

Read: public README and repository metadata on 14 Nov 2026. (Note: `github_api` is not connected in
this session, so this is from `raw.githubusercontent.com` + `api.github.com` over plain fetch, which
is why there is no PR/issue detail here.)

## What it is

* **7,333 stars, 1,075 forks**, Apache-2.0, TypeScript, created Jan 2026, last push 11 Nov 2026 —
  genuinely popular and actively maintained, made by the Craft docs team and used to build their
  own product.
* A **desktop app (Electron + Bun)** for running agent sessions in parallel, with an inbox of
  sessions, per-workspace **skills** (markdown instructions), a **sources** registry (MCP servers,
  REST APIs, local files), three **permission modes** (Explore / Ask to Edit / Auto), **automations**
  (cron and event triggers), and a headless server + CLI that the desktop app can drive remotely.
* Its headline trick: *"tell the agent 'add Linear as a source' — it finds public APIs and MCP
  servers, reads their docs, sets up credentials"* — i.e. **connecting a system is a conversation,
  not an integration project**.
* Credentials live in an encrypted local file (`~/.craft-agent/credentials.enc`, AES-256-GCM);
  the remote server authenticates with a single bearer token.

## The honest answer

**Adopt it for us, not for our customers — yet.**

It is a *single-tenant, single-user* tool: one config directory, one credential store, one server
token, "workspaces" rather than tenants. Concierge is multi-tenant with per-business consent,
audit, and erasure promises. Dropping Craft Agents into the customer path would mean either one
process per client (expensive, and a secret-holding one) or sharing a credential store across
businesses — which would quietly undo the isolation we have been building.

But three of its ideas are worth more than its code, and one of its modes is immediately useful.

### 1. Useful now: our own operator console

Today, diagnosing a tenant means SSH, `psql`, `curl` with the admin token, and remembering our own
routes. Craft Agents can point at **our admin API as a REST source** and our DB behind the existing
jumpbox, with a skill for each job we keep doing by hand:

* *"Explain why support@trendibizz.com's link was refused"* → query `tenant_invites`,
  `/owner/me`, and the last outbox rows, in one answer.
* *"Reissue a link for {slug} and check the email was sent"* → the exact sequence we ran by hand
  three times this week.
* *"Install check on {slug}"* → `widget-config`, hosted page, `install-check`.

That is a half-day experiment with **no customer exposure**, and it removes the most repetitive part
of supporting this product. The desktop app's multi-session inbox is a genuinely nicer shape than
running CLI commands one at a time.

### 2. Steal the pattern: connect by discovery

Our integration backlog (Xero CSV export, quote → job, part payments, calendar per-provider) is
mostly *"connect one more system per customer"*. Craft Agents' model — sources are declared, and an
agent discovers endpoints/docs/credentials — is the direction that turns each new provider from a
dev task into a guided conversation. We would implement it in **our** runtime (a `sources` table, a
connect flow, a review step), not by shipping theirs.

### 3. Steal the pattern: permission modes map onto what we already built

We just made the Permissions screen a per-channel, explicit, withdrawable consent — including "no to
everything". Craft Agents' Explore / Ask / Auto is the same idea at a coarser grain (read-only /
approve each write / act freely). Worth aligning our wording: our chat assistant should have a
visible mode, and "Explore" is a genuinely good sales demo — *"look, it can only read until you say
otherwise"*.

### 4. Steal the pattern: skills as the customisation surface

Per-tenant markdown instructions (tone, rates, what to never say) are how we can tune a customer's
assistant without a deploy. We already have brand voice; formalising it as versioned per-tenant
instructions is cheaper than code paths.

## Where it does *not* fit

| Concern | Why it blocks using it as our customer runtime |
|---|---|
| Multi-tenancy | One `~/.craft-agent` store, one server token, workspaces — not a tenant boundary |
| Secrets | Verified credentials sit in an encrypted **file on the host that runs it**; our model is per-tenant tables with erasure |
| Audit | Session JSONL is a developer log, not a compliance record we can hand a customer |
| Footprint | Electron desktop app; our customers are on phones and cheap laptops |
| Agent powers | Default mode "Ask", but it can run tools, and its own README lists the env-var filtering because subprocesses otherwise leak keys — a warning, not a feature |
| Licensing | Apache-2.0 is fine; "Craft" is a trademark of Craft Docs Ltd, so no white-labelling the name |

## Recommendation

1. **This week (internal, low risk):** stand it up as an operator console against a read-only admin
   token, write two skills — "diagnose a sign-in link" and "run an install check" — and use it on
   the next real support question. Measure: does it cut the time from question to answer?
2. **Next (product, no new runtime):** add a `sources` registry + connect-by-conversation flow inside
   Concierge for the providers we keep being asked for (Xero first), and expose the assistant's
   permission mode in the UI, borrowing the Explore / Ask / Auto vocabulary.
3. **Not now:** embedding Craft Agents as the engine behind the customer-facing assistant. Revisit
   only if we ever offer a self-hosted, single-business install — which is exactly the shape it is
   built for.

**Open question for the operator:** is the goal (a) making *our* support/ops faster, (b) letting
*customers* connect more of their systems with less help from us, or (c) a self-hosted product we
sell to one business at a time? The answer changes which of the three lanes above comes first.
