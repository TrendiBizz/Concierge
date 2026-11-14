# CRM capability audit and the gaps closed — 2026-11-14

## How this was established
An independent read-only audit (a sub-agent with no stake in the outcome) walked every route
decorator in `api/app/main.py`, all 60 `CREATE TABLE` statements in `api/app/schema.sql`, and the
CRM pages in `web/portal/src/`. Its finding, in its words: this is **not** a contacts/companies/
deals CRM — it is a multi-channel enquiry and conversation system with a lead pipeline, quotes and
invoices. There is no `companies`, `deals`, `tags`, `custom_fields`, `notes` or `saved_views` table.

## What was already strong
| Area | State | Evidence |
| --- | --- | --- |
| Person record | Partial | `customer_cases` (name, company, primary phone/email, paused flag), `customer_addresses`, auto-merge on any known address (`casetimeline.reconcile`) |
| Deal | Partial | `leads.status` (`new/contacted/booked/won/lost`), `leads.value_cents`, `won_at`, `lost_at`, `lost_reason`, weighted forecast in `sales.pipeline` |
| Notes/history | Partial | `case_events` unified timeline, `leads.notes`, `tasks.notes` |
| Quotes | **Present** | `quotations` with versioning, expiry, public accept/decline, payment declared, print view |
| Import/export | Partial | `/owner/export/contacts` (CSV/JSON), `/owner/import/contacts` with idempotent dedupe |
| Reporting | Partial | `/owner/revenue` (channel, accept rate, paid/outstanding, vs previous period) |
| Permissions | Partial | roles viewer/editor/owner enforced on writes |
| Automation | Partial | auto follow-up to-dos, SLA alerts, appointment reminders, webhooks with HMAC and retry |

## What was missing, and what was closed today
1. **The pipeline was unreachable from the app.** `PATCH /owner/crm/leads/{lead_id}` existed; no
   page called it. → Enquiries now have **Edit**: stage select, deal value, next-step date, saved
   live with a status line. Proved on production: lead moved to `contacted`, value `480000`.
2. **To-dos were read-only text, and there were no owner routes at all** (only `/admin/...`).
   → `/owner/tasks` GET/POST/PATCH/DELETE, tenant-scoped, plus a "What needs doing" list with
   add, due date and tick-off. Proved live: task 212 created and completed.
3. **Erasure answered the request but did not remove the person.** `privacy.erase` blanked `leads`
   and deleted chat messages, then reported done — while `customer_cases`, `case_events`,
   `appointments`, `quotations`, `phone_calls` and `contact_consents` still held them.
   → `_erase_person_everywhere` anonymises all of them: name/phone/email blanked, conversation
   bodies emptied, quote contact cleared, consent rows deleted, case marked `erased_at`.
4. **Histories could not say who did anything.** `lead_events` had no actor. → `actor` column,
   stamped by the owner route; production row shows `contacted | support@trendibizz.com`.

## Defects found while proving it (fixed, tested, documented)
- `lead_events.actor` ALTER ran before the CREATE on a fresh database — every schema build failed
  with `relation "lead_events" does not exist`. Moved after the table.
- The erasure joined `conversations` on `lead_id`, a column that does not exist (it is
  `session_id`); and `appointments` has no `case_id`/`consent_contact`. Both statements rewritten
  against the real schema, found by the new test rather than in production.
- The erasure test hung forever on first write: a `TestClient` runs the app in its own thread, so
  an asyncpg pool created by `asyncio.run` is bound to a dead loop. Rewritten on
  `httpx.ASGITransport` in one loop, the pattern `test_team.py` already documents.
- **The enquiries table was 1400px wide inside a 1168px panel** — seven fixed 200px columns, so
  the first columns were clipped with no horizontal scroll. Merged the channel into the "Who"
  cell, moved the timestamp under the name, and put both row actions behind one `MoreMenu`:
  now 1112px, fits, **0 clipped cells** in both light and dark mode.

## Proof
- Suite **1185 passing**, including 5 new tests in `api/tests/test_crm_owner_tools.py`.
- Mutation-proofs: removing the erasure call → erasure test red; removing the actor stamp → pipeline
  test red; removing the tenant check on owner to-dos → scoping test red. All restored, suite green.
- Live on production (ACME Ltd): task created + completed via API; deal moved with value; actor
  stamped in `lead_events`; UI Edit → stage select → "Saved. The pipeline and your dashboard use
  this straight away."; to-do added from the page and appeared in the list; no page errors in
  either theme. Screenshots: `crm-pipeline-dark-2026-11-14.png`, `crm-pipeline-light-2026-11-14.png`.

## Round two: assignment and companies (gaps 1 and 2 of six)

**Ownership.** `assigned_to` on `leads`, `customer_cases` and `tasks`;
`PUT /owner/crm/leads/{id}/assignee` and `PUT /owner/contacts/{case_key}/assignee`. An assignee
must be an *active member of this workspace* — a user id from another business is refused with
404, proved by mutation (dropping `tenant_id` from the lookup turns that test red). The contacts
list gained an Owner column; the contact card gained an "Who owns this account" picker.

**Companies.** `companies(id, tenant_id, name, domain, notes, parent_id)` with
`UNIQUE (tenant_id, name)`, plus `customer_cases.company_id`. `GET/POST/PATCH/DELETE
/owner/companies`; each row reports how many people work there, how many deals are open and their
value. Deleting a company **detaches** its people rather than deleting them — proved by mutating
the foreign key to `ON DELETE CASCADE`, which turns that test red. A new **Companies** page in the
Customers group, reachable from ⌘K, with an add form and a per-row menu.

Two defects found by doing it:
- The contact card reloaded the *list* after a save but not the open record, so the picker snapped
  back to "Nobody yet" immediately after assigning someone. Fixed by updating the selected record
  in place; guard `test_the_contact_card_keeps_the_owner_it_just_saved`.
- Restoring a mutation with `git checkout` wiped uncommitted work (the routes and schema for this
  very feature) — a tooling defect, now worked around by committing before mutating and restoring
  from a file copy instead.

Live proof (ACME Ltd, both themes): company created, duplicate name refused with 409, contact
attached, `open_deals: 1`, `open_value_cents: 480000`; contact assigned then unassigned; enquiry
assigned; a foreign user id refused with 404; Companies page renders "Pukeko Construction" and fits
the panel; adding from the form worked; both pickers present and the owner persisted across a
reload; no page errors. Suite **1191**.

## Still missing for "handles everything a CRM must" (ranked, with the file each belongs in)
1. ~~Record ownership / assignment~~ — **done**, see above. — no `assigned_to` anywhere; a team cannot share a queue
   (`schema.sql` + `main.py`; filter `/owner/crm` for editors).
2. ~~Companies as a first-class record~~ — **done**, see above. Parent/child hierarchy exists in the schema but has no UI yet.
3. **Saved views and bulk edit** — no `saved_views` table, no bulk endpoints; every list refilters
   from scratch (`CrmQuotes.tsx`, `main.py`).
4. **Report export** — `/owner/revenue` cannot be exported as CSV/PDF, and there is no
   lost-reason or source breakdown (`revenue.py`, `main.py`).
5. **Attachments and email template library** — inbound mail stores no MIME parts by design;
   templates exist only as per-tenant columns (`email_templates` table + composer).
6. **Sequences** — a campaign is a one-shot send; there is no multi-step follow-up builder.
