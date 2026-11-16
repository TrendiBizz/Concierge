# Wave CRM replacement — build plan (2026-11-16)

**Goal (Jo, 2026-11-16):** "go and look at how we build a replacement for this package, i want it as
close as possible." Target: [wavecrm.com.au](https://wavecrm.com.au) — a membership-management CRM
sold at **AUD $412.85/mo + GST** to Australian chambers of commerce, industry bodies and
associations. Feature inventory and citations: `docs/research/wave-crm-audit-2026-11-16.md`.

This document is the build plan: what we already own, what we must build, in what order, and what
only Jo can decide.

## 1. What Wave sells (and therefore what "close" means)

From the vendor's own pages, Wave is a single platform that replaces a stack. Their words: it
"eliminates MailChimp, Klavyio, Eventbrite, Humanitix, Google Forms, Jot Forms, a variety of
Wordpress plugins" and spreadsheets. The surface, in their own feature list:

| Area | What Wave does |
|---|---|
| Membership records | Member organisations and people, membership types and terms, renewals |
| Payments | Stripe card payments; direct debit for recurring membership; *two-way* Xero sync |
| Invoicing | Invoices from membership and events, reconciled against Xero |
| EDM | Email campaigns to members/subscribers, templates, scheduling, stats, segmentation, personalisation, **no tiered usage** |
| Scheduled comms | Triggered sequences ("drip") on membership events |
| SMS | Broadcast and transactional SMS |
| Events & ticketing | Events, bookings, tickets, member vs non-member pricing, vouchers, dietary requirements, add-to-calendar, "SafeTicket" integration |
| CPD | Track programs, member progress, compliance |
| Member experience | Member self-service portal, profile self-edit, member directory, member-only resources |
| Website | "Integrated homepage" — a self-managed site inside the platform, or embed into an existing one |
| Ops | Migration service, local support, feature requests, flat pricing |

Their differentiator is not depth — it is *one system, no add-ons, flat price, no usage tiers*.
A replacement that matches Wave must therefore be judged on **coverage and consolidation**, not on
having the best CRM.

## 2. What we already have (verified in this repo)

70 tables in `api/app/schema.sql`, 107 app modules, a React portal at `web/portal`, and a small
standalone CRM (`crm/`, SQLite, contacts + pipeline only). The parts that matter here:

| Wave capability | What exists today | Where | Verdict |
|---|---|---|---|
| Contacts / organisations | `leads`, `companies` (tenant-scoped, `parent_id` for hierarchies), `customer_addresses` | `api/app/schema.sql` | **Reuse** — map member org → `companies`, member person → `leads`; do not invent a second contact store |
| Membership & renewals | nothing (`membership` appears in 0 modules, 0 tables) | — | **Build** |
| Multi-tenancy, users, roles | `tenants`, `tenant_users`/`tenant_sessions` with `viewer/editor/owner`, invites, login limits | schema | **Reuse** |
| Email campaigns | `campaigns.py` (281 lines): consent-gated audience, draft→preview→send, recipient caps, per-hour spread, per-campaign preview freeze, kill switch; `email_templates`, `email_engagement`, `opt_outs`, `unsub` | `api/app` | **Reuse engine, build EDM authoring/stats on top** |
| SMS | `sms`, `device_sms_*`, `sms_devices`, quiet hours + STOP handling in the outbox | `api/app` | **Reuse** |
| Triggered sequences | `sequence` logic inside `automation.py`/`campaigns` (3 modules), `lead_events`, `case_events` | `api/app` | **Extend** with membership triggers |
| Invoicing | `invoices`, `quotations`, `quote_profiles`, `billing.py` (references, issue details, validity) | `api/app` | **Reuse** for membership + event invoices |
| Payments | Stripe (deposit/plan links), `quote_payments`, `platform_invoices` | `api/app`, `payments/` | **Reuse**, add subscription renewal charging |
| Events & ticketing | `appointments`, `booking.py`, `calendar_connection` — **scheduling, not ticketing** (no `event`/`ticket` tables) | `api/app` | **Build** ticketing; reuse calendar + email/SMS notifications |
| CPD | nothing | — | **Build** |
| Member portal / self-service | `web/portal` React app (Companies, Quotes, Engage, Texts, Products, Designs...) — owner-facing, not member-facing | `web/portal` | **Build** member-facing surface, reuse tenancy/auth |
| Member directory & resources | nothing | — | **Build** |
| Website / CMS | the platform *is* a site generator: `website/` + `scripts/seo/site_seo.py` gate, deploy manifest, IndexNow | `website/`, `scripts/` | **Reuse pattern, not code** — a per-tenant site would share the SEO contract and deploy machinery |
| Xero | **nothing** — the only mention is a blocklist entry in `automated_mail.py` | — | **Build** (greenfield, highest-risk item) |
| Analytics/reporting | partial (`casetimeline`, `engagement`, `reports` exports) | `api/app` | **Build** per-domain dashboards |

Two structural decisions fall out of this:

1. **Build on `api/app` + Postgres, not on `crm/`.** `crm/` is a deliberate 500-line
   contact+pipeline tool on SQLite with no email, no payments, no tenancy roles beyond a passcode.
   Wave parity needs the 70-table system's consent, outbox, invoices and tenancy. `crm/` stays as
   the small-business CRM product.
2. **Members are not leads.** A lead is an enquiry; a member is an organisation with a contract,
   a term, invoices, directors, a directory listing and a compliance record. Keeping them in the
   same table would corrupt the sales pipeline's meaning. Shared *person/company identity* yes
   (`companies`, and a person record), shared *status lifecycle* no.

## 3. Data model to add

New tables (sketch, tenant-scoped like everything else):

```sql
membership_types   (id, tenant_id, name, code, price numeric, currency, period text, term_months int,
                    joining_fee numeric, pro_rata bool, xero_item_code text, active bool)
members            (id, tenant_id, company_id, member_no text, type_id, status text,               -- applicant|active|lapsed|resigned|suspended
                    joined_on date, renews_on date, billing_contact_id,        -- FK leads
                    stripe_customer_id text, xero_contact_id text,
                    directory_optin bool, gst_exempt bool, notes, created_at, updated_at)
member_people      (id, tenant_id, member_id, lead_id/contact_id, role text, is_primary bool)      -- directors, reps
membership_periods (id, member_id, starts_on, ends_on, type_id, price, status, invoice_id,
                    renewed_at, churn_reason)                                                   -- the renewal ledger
cpd_programs       (id, tenant_id, name, year, required_points numeric, rules jsonb)
cpd_activities     (id, tenant_id, program_id, name, points, category, evidence_required bool)
cpd_records        (id, tenant_id, program_id, member_id, activity_id, points, completed_on,
                    evidence_url, status text, approved_by, approved_at)                        -- pending|approved|rejected
cpd_cycles         (id, tenant_id, member_id, program_id, year, target, awarded, status, due_on)    -- compliance roll-up
events             (id, tenant_id, slug, name, starts_at, ends_at, venue, capacity,
                    member_price numeric, non_member_price numeric, status, page_html, xero_item_code)
event_tickets      (id, tenant_id, event_id, name, price, member_only bool, allocation int)
event_registrations(id, tenant_id, event_id, ticket_id, member_id, name, email, qty, amount,
                    dietary, voucher_code, stripe_payment_intent, checked_in_at, created_at)
event_addons?      (skip: dietary/voucher are columns above until proven otherwise)
directory_listings (id, tenant_id, member_id, category, blurb, logo_url, website, phone,
                    published bool, updated_at)                                                -- member self-edited
resources          (id, tenant_id, title, body_md/html, file_url, visibility text,             -- public|members|type:gold
                    member_types text[], published_at)
resource_views     (id, tenant_id, resource_id, member_id, viewed_at)                            -- "who reads what"
web_sites          (id, tenant_id, domain, page_json jsonb, theme jsonb, published_at)           -- integrated homepage
xero_connections   (id, tenant_id, tenant_xero_id, access_token_enc, refresh_token_enc,
                    expires_at, scopes text[], last_sync_at, status)
xero_object_map    (tenant_id, local_table, local_id, xero_type, xero_id, synced_at)             -- the two-way key
```

Notes that will bite later if ignored:

- **Renewals need a ledger, not a `renews_on` column.** `membership_periods` is what makes
  "renewal rate", "lapsed 30 days" and "revenue by cohort" answerable, and it is what Wave's
  customers actually buy the product for.
- **Money stays numeric/decimal with currency, GST-exempt flag per member** — the GST bug from the
  pricing work applies with interest once invoices multiply.
- **Every member-facing page is tenant-scoped and directory fields are opt-in**, or a chamber's
  member list becomes a scraped lead list.
- **`xero_object_map` is the two-way contract.** Xero reconciliation is the feature Wave's buyers
  name; a one-way push is not parity.

## 4. Milestones, with the acceptance test for each

| # | Milestone | Ships | Acceptance (must fail before, pass after) |
|---|---|---|---|
| M1 | Membership core | `membership_types`, `members`, `member_people`, `membership_periods`; admin CRUD; CSV/legacy import with dry-run diff; renewal date maths incl. pro-rata; status transitions with audit | Import a 300-row legacy spreadsheet twice → second run is a no-op, first is a diff summary; a lapse and a renewal both produce exactly one period row |
| M2 | Billing wired | invoice generation per period (reuse `invoices`), Stripe subscription/charge for renewals, reminders (email + SMS via `outbox`), dunning ladder | A member renews end-to-end in staging; invoice matches period; reminder respects quiet hours and STOP |
| M3 | Member portal | login (invite via existing `tenant_invites` pattern), profile self-edit, invoice history + pay, directory control, resources | Member edits their profile and an unrelated tenant cannot read it; a directory opt-out disappears from the public list within one request |
| M4 | EDM + sequences | campaign authoring UI over the existing engine, segments (type, status, region, CPD status, tags), templates, per-send stats, membership-triggered sequences | A segment of "lapsed 30d, marketing consent" sends once, respects the preview freeze, and a consent-removed contact is excluded |
| M5 | Events & ticketing | `events`, `event_tickets`, `event_registrations`; public event pages, member/non-member pricing, vouchers, dietary, QR check-in, add-to-calendar | Member price applies only with a live membership; a sold-out event refuses one more seat; check-in is idempotent |
| M6 | CPD | programs, activities, records with evidence upload, approval, cycle compliance report | A member's points roll up correctly and a cycle with missing evidence shows non-compliant |
| M7 | Xero two-way | OAuth connect, contact/item mapping, invoice + payment sync both ways, reconciliation view | Create in Wave → appears in Xero; mark paid in Xero → Wave reconciles without a duplicate; replay is idempotent |
| M8 | Website per tenant | page builder over `web_sites`, shared SEO gate (`site_seo.py` contract), sitemap/IndexNow per tenant | A tenant site passes the same technical SEO check as trendibizz.com |

M1–M3 is the "a chamber could move" line. M4–M5 is what makes them stay. M7 is what unblocks the
sale to any Australian association, and is also the riskiest (Xero OAuth, token storage, mapping).

## 5. Reuse map, concretely

- **Consent/quiet-hours/kill-switch**: `campaigns.py` + `outbox` already encode the safe-send rules
  (marketing consent, opt-outs, signed unsubscribe, STOP, per-hour spread, kill switch). Membership
  mail must go through the same path — do not build a second sender.
- **Invoices**: `invoices` + `billing.py` references; add `invoice.kind` (`membership`, `event`,
  `cpd`) and `membership_period_id`.
- **Stripe**: existing patterns for links and payment intents; renewal charges need a customer +
  payment method on file, which is new (current flow is hosted links).
- **Portal**: `web/portal` is Vite/React and already handles tenant auth, quotes, products. The
  member-facing area should be a second app or a route group with a *member* session type — do not
  reuse owner sessions.
- **SEO for tenant sites**: `scripts/seo/site_seo.py` is the contract that keeps trendibizz.com
  honest; reuse it per tenant site.
- **Tests**: `api/tests` (1420 passing) — new modules get tests in the same style; the repo's rule
  is fix+test+document in-session.

## 6. Decisions only Jo can make

1. **Product or internal tool?** Selling this to Australian chambers means Australian data
   residency (Wave leans on "data sovereignly in Australia"), a privacy-policy commitment under the
   Australian Privacy Act, and AUD pricing. Selling it to NZ chambers changes both. *Recommend:
   decide the market before M1, because it fixes hosting and pricing.*
2. **Same repo or new repo?** This repo is bound to the deployed trendibizz.com system (deploy
   scripts, health checks, manifest). A second product inside it will make every deploy gate carry
   both. *Recommend: new repo, sharing the `api/app` patterns and the SEO contract by copy, with
   this plan copied across.*
3. **Xero first or last?** It is the parity feature least likely to be bought twice and the most
   expensive to fake. *Recommend: build M7 after M3 has a real pilot chamber.*
4. **Ticketing: build or wire SafeTicket?** Wave owns SafeTicket. We do not. Building ticketing is
   M5; wiring an existing provider is faster but not "as close as possible".
5. **Pricing and term:** Wave is $412.85/mo + GST with a minimum term and "unlimited members".
   Pick the comparable number, including whether migration is included.

## 7. Effort shape (rough, one senior dev + one AI pair)

- M1 2 weeks · M2 2 weeks · M3 2.5 weeks · M4 2 weeks · M5 3 weeks · M6 1.5 weeks · M7 4 weeks ·
  M8 3 weeks → **~20 weeks to parity at a pace that also tests**, of which Xero and ticketing are
  half the risk. A pilot chamber could be migrated after M3 (~6.5 weeks).

## 8. Non-goals (deliberately)

- No general-purpose CRM (that is `crm/`), no marketing automation beyond membership triggers, no
  LMS (CPD is evidencing, not teaching), no website migration service, no Phone/SMS AI receptionist
  (that is Concierge — it can be *sold alongside*, not fused).
