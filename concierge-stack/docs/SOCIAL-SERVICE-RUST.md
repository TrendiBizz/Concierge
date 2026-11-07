# Concierge Social: a small Rust service (design and status)

## Verified implementation update (2026-11-07, local commit in progress)

The older implementation plan below is historical and contains stale wording.
The current source of truth is `social-service/README.md` and the actual code.

Implemented now: `model.rs`, `store.rs`, `connector.rs`, `scheduler.rs`,
`api.rs`, `main.rs`, `bluesky.rs`, vault and guardrails; 23 automated tests
(including Bluesky serialization, tenant isolation, approval tokens,
HTTP authorization and a mock publish path), plus local HTTP smoke test.
The default server cannot publish to a live network.

Bluesky has a pilot-only app-password connector. **This is not a seamless OAuth
customer connection**, and real network posting has not been tested.
OAuth and all other social platforms remain outstanding. A real customer
should never be enrolled until scoped API authentication, the portal OAuth flow,
consent/approvals and recovery have been tested.

The service reimplements required features independently using official APIs.
Postiz source and its AGPL-3.0 licence are not imported, translated or embedded.
Do not deploy or enable publishing based solely on a passing offline test.


Jo's brief (2026-11-07): social linking and posting must be integrated cleanly into Concierge, invisible to the customer, as
seamless and painless as possible, with nothing we do not need. Where existing code must change to be simpler, do it in Rust.

## The decision

We do NOT run Postiz (nine containers, Temporal, Elasticsearch, a full web app) and we do NOT port its code.
We write a small Rust service, `concierge-social`, from the networks' OFFICIAL API documentation.

**Why not port Postiz?** It is AGPL-3.0. Translating its source into Rust would make our code a derivative work that we would
have to offer to everyone using it over a network. Writing from the official docs avoids that. From Postiz we take only the
architecture ideas (one organisation per customer; one install-wide set of developer apps; the public API keyed per customer),
which are ideas, not code. Rule for whoever works on this next: do not copy from or translate Postiz source.

## What it is

One static binary and one SQLite file. Rust crates only: tokio, axum, rusqlite (bundled SQLite), serde, aes-gcm, regex, time,
rand, base64, async-trait. A real HTTP client is added with the first real connector. No UI. No analytics. No team features.
No AI image or video generation. No queue server. Nothing the customer sees.

| Piece | Job |
|---|---|
| `vault` | AES-256-GCM encryption of every access and refresh token at rest, bound to its account (Postiz keeps channel tokens as plain strings, as far as the schema shows) |
| `guardrails` | SocialSync's core idea, ported from Jo's own code: platform limits, verified facts, forbidden phrases, warnings, per customer |
| `model` | The post lifecycle as a state machine: draft, pending approval, approved, scheduled, publishing, published, failed, rejected |
| `store` | SQLite. Every query is scoped by customer. Audit log of every step. |
| `connector` | One small trait per network (`publish`), honest errors: retryable, permanent, needs re-login |
| `scheduler` | Publishes due posts, retries with back-off, never publishes anything that was not approved |
| `api` | JSON API for Concierge and Hermes, two keys with different powers |

## How "nothing posts until the customer says yes" is made structural

1. A post can only reach `scheduled` through `approved`, and `approved` can only be reached by the approval step.
2. The approval is tied to a **revision** number. Editing the text bumps the revision and sends the post back to draft, so
   what is published is exactly what the customer approved. The scheduler re-checks this before every publish.
3. Two API keys. The **agent key** (Hermes) can read rules, check, create and edit drafts, and submit them. The **Concierge
   key** can create customers, register accounts, request an approval token, and approve or reject. Hermes cannot publish,
   even with a token in hand.
4. Approval tokens are random, single-use and expire.

## How it plugs into Concierge (invisible to the customer)

- The customer never sees this service. They see Concierge: the phone assistant, text and email. Connect pages are served on
  Trendi's own domain, so the OAuth screens are the network's own, reached from a Concierge link.
- Hermes drafts posts and calls the agent key. When a draft passes the guardrails it is submitted. Concierge's existing
  notifier (`notify.py`, with its honest `sent / failed` statuses) sends the customer the draft text by their chosen channel
  (text or email), and a reply of YES calls the approval endpoint.
- Customer data, tokens and the audit log are one SQLite file, included in the encrypted backups.

## Status

Built and tested in the first slice (this commit): vault, guardrails, state machine, store, scheduler with a mock connector,
API with role separation. NOT built yet: the real connectors and the OAuth connect flow, in this order: Bluesky (no approval),
Mastodon, LinkedIn personal, X, then Meta, LinkedIn pages, Google Business Profile, TikTok, Pinterest as approvals land
(see `SOCIAL-NETWORKS-ACCESS.md`); the Concierge side that sends the approval message and reads the reply; media upload.

## Run

```
cd concierge-stack/social-service && cargo test          # tests
SOCIAL_VAULT_KEY=$(openssl rand -base64 32) SOCIAL_CONCIERGE_KEY=$(openssl rand -hex 32) SOCIAL_AGENT_KEY=$(openssl rand -hex 32) \
  cargo run --release                             # listens on 127.0.0.1:4390 only
```

## Implementation plan (for the next session; decisions already made)

Status check: `vault.rs` and `guardrails.rs` are written and `cargo check` passes (2026-11-07). No tests yet. Write tests as you go.

**`model.rs`.** `Status` enum (snake_case): `Draft, PendingApproval, Approved, Scheduled, Publishing, Published, Failed, Rejected`, with
`can_move_to`. Allowed moves: Draft to PendingApproval; PendingApproval to Approved, Rejected or Draft; Approved to Scheduled or Draft;
Scheduled to Publishing or Draft; Publishing to Published, Failed or Scheduled (retry); Failed to Scheduled or Draft; Rejected to Draft.
Structs: `Post { id, customer_id, content, link, hashtags, account_ids, media, status, scheduled_at, revision, approved_revision,
attempts, last_error, created_at, updated_at }`, `NewPost`, `Customer { id, name, rules, approval_contact, created_at }`,
`Account { id, customer_id, network, display_name, external_id, needs_reauth, expires_at }`.

**`store.rs`** (rusqlite, one `Mutex<Connection>`, `open(path)` and `open_memory()`). Tables: `customers(id, name, rules_json, approval_contact,
created_at)`, `accounts(id, customer_id, network, display_name, external_id, token_enc, refresh_enc, expires_at, needs_reauth, created_at)`,
`posts(...)` as the struct, `post_results(post_id, account_id, ok, external_post_id, error, at)`, `approvals(token PK, post_id, revision,
scheduled_at, created_at, expires_at, used)`, `events(at, customer_id, post_id, kind, detail)` as an audit log. EVERY read and write is scoped by
`customer_id`. Status changes are `UPDATE ... WHERE id AND customer_id AND status = from` and fail with Conflict if 0 rows changed. Editing a
post bumps `revision`, clears `approved_revision` and `scheduled_at`, and returns it to Draft (not allowed while Publishing or Published).
`create_approval` needs PendingApproval, stores the revision and requested time, one live approval per post, random 24-byte base64url token.
`decide_approval(token, approve, now)` in one transaction: token unused and unexpired, post still PendingApproval with the SAME revision;
approve sets Approved with `approved_revision = revision` then Scheduled at the requested time (or now); reject sets Rejected.
Account tokens are sealed by the caller with `vault::account_label(customer, network, external_id)` before they reach the store.

**`connector.rs`.** `#[async_trait] trait Connector { fn network(&self) -> &'static str; async fn publish(&self, PublishRequest) -> Result<Published, ConnectorError>; }`.
`PublishRequest { external_id, access_token, refresh_token, text, link, media }`, `Published { external_id, url }`,
`ConnectorError { Retryable(String), Permanent(String), AuthExpired(String) }`, a `Registry` keyed by network, and a `MockConnector`
(configurable failure, records what it was asked to publish) for tests. A post to a network with no connector fails as Permanent.

**`scheduler.rs`.** `run_due(store, vault, registry, now)`: fetch Scheduled posts due now, claim each (Scheduled to Publishing, attempts + 1),
REFUSE to publish unless `approved_revision == revision` (defence in depth), skip accounts that already have a successful result, decrypt tokens,
publish per account, record results. All ok: Published. Retryable and attempts under 5: back to Scheduled with back-off. Permanent: Failed with the
reason. AuthExpired: mark the account `needs_reauth`, Failed with a clear message so Concierge can ask the customer to reconnect. `run_forever` ticks
every 15 seconds.

**`api.rs`** (axum 0.7, so path params are `/:id`). Two Bearer keys, constant-time compared:
agent key (Hermes) and Concierge key. Routes: `GET /health` (no auth);
agent or Concierge: `GET /v1/customers/:c/rules`, `POST /v1/customers/:c/check`, `POST|GET /v1/customers/:c/posts`, `PUT /v1/customers/:c/posts/:id`,
`POST /v1/customers/:c/posts/:id/submit` (Draft to PendingApproval, only if the guardrail check has no errors), `GET /v1/customers/:c/accounts`;
Concierge only: `POST /v1/customers`, `PUT /v1/customers/:c/rules`, `POST /v1/customers/:c/accounts`, `POST /v1/customers/:c/posts/:id/approval-request`
(returns the token and the exact text to show the customer), `POST /v1/approvals/:token/approve` (body may carry `scheduled_at`, RFC 3339) and `/reject`.
The agent key must get 403 on every Concierge-only route, even holding a valid token.

**`main.rs`.** Env: `SOCIAL_DB` (default `./data/social.db`), `SOCIAL_BIND` (default `127.0.0.1:4390`), `SOCIAL_VAULT_KEY` (base64, 32 bytes),
`SOCIAL_CONCIERGE_KEY` and `SOCIAL_AGENT_KEY` (at least 16 characters each and different). Refuse to start on any problem. Spawn the scheduler. Bind loopback only.

**Tests (`tests/`).** vault round trip, tampered ciphertext, label mismatch; guardrails (over limit, X link length, Instagram needs media, hashtags, fact
contradiction, forbidden phrase, warning not blocking); state machine (cannot reach Scheduled without approval, token single use and expiry, editing after
approval resets to Draft, scheduler refuses a revision mismatch, retry and back-off, partial success); customer isolation; API role separation using
`tower::ServiceExt::oneshot`.

**Connectors after the foundation** (official docs only; see `SOCIAL-NETWORKS-ACCESS.md`): Bluesky first (OAuth with DPoP and PAR needs no approval; an app
password is the simpler first step for the test account), then Mastodon, LinkedIn personal (`w_member_social`), X (`POST /2/tweets`, pay per use),
then Meta, LinkedIn pages, Google Business Profile, TikTok, Pinterest as approvals arrive. Add `reqwest` (rustls) with the first connector, and keep
OAuth connect pages on Trendi's own domain. Instagram and others have no native scheduling in the docs: our scheduler covers it.
