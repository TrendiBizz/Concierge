# What a system like this must have — and where ours falls short

Final check, comparing Concierge against the systems a tradesman would otherwise buy: **Jobber**,
**ServiceM8**, **Tradify**, **Fergus**, **Buildxact**, **Payaca** and **GoHighLevel**, plus the New
Zealand rules that apply to quotes, invoices and personal information. Sources at the end.

Method: read the schema (61 tables) and the router list, then probed for each capability by name —
a capability with no table and no route does not exist, whatever the UI says. Everything marked
"has" below was then exercised live.

## What we already have (verified, not assumed)

| Area | Status |
|---|---|
| Multi-channel capture — chat, email, SMS, inbound calls, missed-call recovery | has |
| CRM: enquiries, contacts, addresses, transcripts, recordings, call insights | has |
| Quotations: draft → reviewed sign-off → accepted / declined, public link, version, print | has |
| **Quote as a document** — reference, valid-until, issuer, GST number, NZBN, terms | **added this session** |
| Payments without a processor: instructions, "I have paid", owner confirmation | has |
| Products and stock movements | has |
| 3D model takeoff → priced quote (IFC) | has, unique to us |
| Rate cards per measurement basis, waste %, minimum charge, GST | has |
| Diary, appointments, ICS feed, tasks | has |
| Team roles (owner / editor), passwordless sign-in, session table | has |
| Social publishing, approval-first, seven networks | has |
| Outbox with retries, opt-outs, quiet hours, dedupe | has |
| Portability/export and retention | has |
| Onboarding wizard, in-product guides, PWA push | has |

## Where we fall short

| # | Capability | Competitors | Severity | Our position |
|---|---|---|---|---|
| 1 | **Invoice / tax invoice from an accepted quote** | all of them | **High** | None. A quote can be accepted and marked paid, but no invoice document is ever produced. NZ tax invoices need supplier name, GST number, date, description, GST amount. |
| 2 | **Backups off the machine** | table stakes | **High** | Backups *do* exist: `backup-all.sh` daily at 14:30 UTC, 14 archives retained, ~60 MB each, covering concierge + CRM dumps and shared assets. Restore verified this session. Remaining gap: they live on the same disk as the database — a disk failure, ransomware or a deleted directory loses both. |
| 3 | **Alert delivery** | table stakes | **High** | `healthcheck.sh` (every 5 min) and `watchdog.py` (every 10) run and log, but the VPS has **no MTA** — no sendmail, no msmtp, no `mail` — so cron's failure mail was discarded. Every alert was silently dropped. **Fixed this session** (see below). |
| 4 | **Privacy Act 2020 surface** — privacy statement, retention stated, deletion on request | all SaaS | **High** | Retention code exists but no public privacy page, no delete-my-data path, no consent record per contact. We store call recordings and transcripts. |
| 5 | **Accounting integration (Xero)** or accounting-shaped export | Tradify, Fergus, Buildxact, ServiceM8 | **High** (NZ) | None. Nothing reaches a bookkeeper without retyping. A CSV in Xero's invoice format is the cheapest real answer. |
| 6 | **Quote → job** with schedule, progress and photos | Jobber, ServiceM8, Tradify | Medium-High | Appointments exist, but there is no "accepted → job" object, no photos against a job, no completion record. |
| 7 | **Cost vs sell price (margin)** | Buildxact, Fergus | Medium | Rate cards hold the sell rate only. No supplier cost, so nobody can see whether a job made money. |
| 8 | **Deposits / progress payments** | Jobber, Payaca, Tradify | Medium | One "paid" state, no schedule of 50/40/10, no per-stage invoicing. |
| 9 | **Installable mobile app** | all of them | Medium | `push_subscriptions` exists but there is no web manifest or service worker — it can't be added to a phone home screen properly, and it won't open without signal. |
| 10 | **Time tracking** (labour on a job) | ServiceM8, Fergus, Tradify | Medium | None. |
| 11 | **Audit trail of who changed what** | all business SaaS | Medium | Only channel authorisations and payments are audited; editing a quote leaves only a version number. |
| 12 | **Quote acceptance with a name/date record** | Payaca, GoBuild | Low-Medium | Acceptance is a click; no typed name, no timestamped certificate. Weak if a dispute arises. |
| 13 | **Multi-factor on owner accounts** | expected of finance software | Low-Medium | Passwordless magic links (single-use, 30 days). No second factor, no "sessions I'm signed in on" screen. |
| 14 | **Win/loss reporting** | Jobber, Tradify | Low-Medium | Revenue exists; no conversion rate, no lost-reason capture. |
| 15 | **PDF/DWG takeoff** | PlanSwift, Buildxact | Low (deliberate) | IFC only. Stated honestly in the guide and the email. |
| 16 | **SMS compliance for NZ (UEMA)** | all local players | Low | Opt-outs and suppressions implemented; no documented sender-ID/consent process. |

## Fixed in this session (essential, so not left on the list)

**A quotation was not a document.** It had a title, some lines and a total: no reference, no
validity date, no issuer name, no GST number, and no terms. That fails the basic "quote you can
send a customer" test every competitor passes.

* `billing.py` — reference counter (`PUKE-0001`, atomic per business), validity window (default 30
  days, clamped 1–365), issuer details, expiry test.
* `tenants` gained `gst_number`, `nzbn`, `business_address`, `business_phone`, `quote_terms`,
  `quote_valid_days`, `quote_sequence`; `quotations` gained `reference` and `valid_until` (unique per
  business).
* Every quotation — hand-written or from a model — gets a reference and a validity date.
* The customer page and the print view now show the issuer block, the reference, "Valid until", and
  the terms.
* Expired quotes cannot be accepted: the button disappears **and** `POST /quote/{token}/accept`
  answers `409`.
* `GET/PUT /owner/business` plus a "Your business details" card in Quotes.

**Live proof** (test quote `TREN-0901` on `trendi-support`, since deleted): page contained the
reference, valid-until, GST number, address, phone, terms, customer name and the accept button; on
backdating `valid_until` the button vanished and accept returned
`409 {"detail":"This quotation has expired — ask for an updated one"}`. 8 new tests; **1083 pass**.

## Fixed this session, second pass

**Alerts had nowhere to go.** `healthcheck.sh` exits non-zero on failure and cron tried to mail
root, but there is no mail transport on the host, so nothing was ever delivered — the exact silent
failure the health check exists to prevent.

* `scripts/vps/alert.sh` — sends the failing check to `admin@trendibizz.com` over the external SMTP
  relay the product already uses, run from the host so it works when the containers are down, with
  hourly suppression so an outage is not a flood. Verified: simulated failure → "alert sent to
  admin@trendibizz.com".
* Cron rewritten: `healthcheck.sh > /tmp/healthcheck.json || alert.sh < /tmp/healthcheck.json`.

**Restore had never been tested.** `scripts/vps/restore-drill.sh` extracts the newest archive into a
scratch database, reports what came back, and drops it. Run now: **4 businesses, 27 enquiries, 49
messages, 4 users recovered** from the 2026-11-12 archive. Scheduled weekly (Sundays 03:30).

## Recommended order of work

1. **Off-host backup copy** — the remaining High item: point `backup-all.sh` at object storage (or
   rsync to a second machine) so one disk cannot take the database and its backups together. Needs a
   destination and credentials from the operator.
3. **Invoice from an accepted quote** — one new document using the same billing block; unlocks 4.
4. **Xero-shaped CSV export** — reuses `portability.py`; makes the product bookkeeper-friendly.
5. **Privacy page + delete-my-data path** — legal exposure we are carrying today.
6. **Quote → job, photos, completion** — turns quotes into a workflow.
7. Deposits, margin, manifest/service worker, time tracking, in that order.

## Sources

- [Commerce Commission — quotes, estimates and invoicing](https://www.comcom.govt.nz/business/dealing-with-typical-situations/quotes-estimates-and-invoicing/)
- [Consumer Affairs — getting quotes and estimates](http://www.consumeraffairs.govt.nz/for-consumers/services/getting-quotes-and-estimates/pdf/getting-quotes-and-estimates.pdf)
- [Tradie Scaler — software pricing comparison: ServiceM8 vs Tradify vs Fergus](https://tradiescaler.com/tools/software-pricing/)
- [Tradie Scaler — quoting/estimating alternatives](https://tradiescaler.com/quoting-estimating/quotient-alternatives/)
- [Payaca — service business app listing](https://play.google.com/store/apps/details?id=com.payaca.mobileapp)
