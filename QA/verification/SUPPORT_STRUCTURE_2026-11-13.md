# Trendi support structure — 2026-11-13 (first version)

Status key: **LIVE** works now · **TODO** not built · **DECIDE** needs the operator.

## 1. Channels

| Channel | Address / route | State |
|---|---|---|
| Support email | `support@trendibizz.com` → Cloudflare rule "Support intake" → `concierge-inbound-worker` → (a) platform draft in the Trendi tenant, owner alert; (b) original forwarded to the operator's inbox | **LIVE** since 2026-11-13 ~13:10 NZDT. Before that it fell into the catch-all forward only: no record, no alert |
| General email | `admin@trendibizz.com` → same worker. Standard From address for everything the platform sends (operator decision) | **LIVE** |
| Website form | opens an email draft to `admin@`; the page also names `support@` | **LIVE** (wording is now true) |
| Phone | +64 9 243 1347, AI assistant answers, owner alert by email | **LIVE** (staging tenant); SMS alerts **broken** (phone offline) |
| Chat widget | site assistant | **LIVE** |

Rollback for the support route: delete Cloudflare rule `8db03a2cc01f4c97935ed313f73f048c` (mail goes back to the catch-all forward) and
`delete from inbound_mailboxes where recipient='support@trendibizz.com';`.

## 2. Who and how fast

* Owner of the queue: the operator (**DECIDE** a named backup; today this is a single point of failure).
* Customer promise (published on the contact page): a reply within one business day. Keep it; do not shorten it publicly yet.
* Internal targets (**DECIDE**, proposed): P1 outage or safety problem, same business hour; P2 customer cannot use a paid feature, 4 business hours; P3 question, one business day.
* Hours and out-of-hours message: **TODO** (state NZ business hours; an out-of-hours auto-acknowledgement).

## 3. Triage (label in Gmail `Trendibizz/Support`; draft appears in the platform)

1. **Outage or data/safety** (calls, texts, emails not arriving; a message loop; anything leaking) → P1, act first, then reply.
2. **Onboarding help** (invite, consent, number, alerts) → P2, use the go-live checklist in the handoff.
3. **Billing or account** → P2.
4. **Privacy requests** (access, correction, deletion) → record the date; Privacy Act 2020 allows 20 working days; never send personal data to an unverified address.
5. **Security reports** → P1, acknowledge within one business day; **TODO** publish `security.txt` and decide a `security@` alias.
6. **Sales enquiry** → follow up as a lead. **Solicitations/spam** → label `Solicitations`, no reply.

## 4. Built-in safeguards that apply to support mail

Own-mail loop guard, per-mailbox flood limit (60/hour), per-sender limit (10/hour, quarantines for review), DKIM/DMARC checks, virus scan,
automated senders get no auto-reply, outbound flood guard and kill switch. `email_auto_reply` stays **off**: nothing is sent to a customer
without a person approving it.

## 5. To build next (in priority order)

1. **Test it now:** send one email from a normal inbox to `support@`; expect a draft in the Trendi tenant, an owner alert, and the original in the inbox.
2. Acknowledgement email with a reference and the one-business-day promise (opt-in, after the test passes; must never answer robots).
3. Reply templates for the six categories above; a support knowledge base the assistant can quote.
4. Track response time: set `sla_minutes` for the Trendi tenant (today 0 = off) so overdue support mail alerts the operator.
5. Dedicated Trendi support tenant (today support shares the staging tenant `trendi-oauth-staging`; the operator must own its consent records).
6. Status page and an out-of-hours message; a named backup person; `security.txt`.
7. Fix the SMS alert path (phone device) so a P1 alert can reach a phone, not only email.
