# Round three: the remaining CRM gaps, and a system-wide recheck — 2026-11-14

## What was built (closing the last four of the six audit gaps)

| Gap | What now exists | Proof |
| --- | --- | --- |
| Bulk edit | `POST /owner/contacts/bulk-assign` (up to 200 keys at once, tenant-scoped, refuses a member of another business). Contacts gained a tick-box column and an "Assign selected to" bar. | `test_a_batch_of_contacts_can_be_given_one_owner`, `test_a_foreign_batch_cannot_be_assigned_into_our_business`; live: "Assigned 1 person." |
| Report export | `GET /owner/reports/export.csv` — enquiries by stage + channel + **lost reason** + value, and quotes by status. Reports page carries a "Take it with you" download. | `test_the_report_can_leave_the_app_with_lost_reasons_and_sources`; live download named `concierge-report.csv` with the real header row |
| Template library | `email_templates` table and `GET/POST/PATCH/DELETE /owner/email-templates`, tenant-unique names, its own **Saved replies** page. | `test_saved_replies_can_be_written_reused_and_deleted`; live: saved and still there after a reload |
| Sequences | **Not built.** See "Deliberately not built" below. | — |
| Company hierarchy | `PATCH /owner/companies/{id}` now honours `parent_id`, including clearing it; a "Part of" select on each row. | `test_a_branch_company_points_at_its_parent_and_refuses_another_business`; live: nested, listed, un-nested |

## Defects found while doing it — all fixed, tested, documented

### 136. Every visitor got "Internal Server Error" during a portal deploy (P1)
Production logs showed eight `PermissionError: [Errno 13] Permission denied: '/srv/studio/index.html'`.
Cause: the portal was rsynced with `-a` (which preserves the uploading user's permissions as files
land) and `chmod -R a+rX` ran only *after* the copy finished. In that window the API user could not
read the page. The route asked `is_file()` — "does a regular file exist" — which is not the same
question as "can I open it", so the `PermissionError` escaped the handler.
Fix, both halves:
- **Product**: `_readable()` opens the file to answer the real question. An unreadable index now
  serves a 503 "One moment, we are updating the app" page with `Retry-After: 5`; an unreadable or
  missing asset is a 404. A customer never sees a bare 500.
- **Tooling**: `scripts/vps/deploy-studio.sh` stages the build, sets permissions *before* anything
  goes live, rsyncs with `--chmod` and `--delay-updates`, then requires three consecutive 200s and
  fails loudly otherwise.
Mutation-proofs: reverting to `is_file()` turns the 503 test red; removing `--chmod` turns the
deploy-script test red. Both restored.

### 137. A company could be nested but never un-nested
`PATCH /owner/companies/{id}` filtered every `None` out of the payload as "not provided", so
`{parent_id: null}` became "Nothing to update" and the page silently kept the old parent. Found by
driving the live API by hand, not by the test suite (which only covered setting a parent).
`parent_id` is now a real instruction when present. Guard nests, un-nests, re-reads the list.

### 138. The report download answered 401 in a blank tab
The button used `window.open`, which sends no credentials. Auth here is a bearer token in memory,
not a cookie — the contacts export already documents this exact trap, and I walked into it anyway.
Now fetched with the header and handed to the browser as a blob. Guard:
`test_the_report_button_fetches_with_the_token_instead_of_opening_a_bare_tab`; live download checked.

### 139. Saved replies were reachable only by walking the setup wizard again
They were mounted inside step 3 of onboarding, so an established business could not find them. Moved
to their own Settings page, reachable from the sidebar and ⌘K.

### 140. The CAD customer picker had no accessible name
`Designs.tsx`'s `<select>` sat under a paragraph with no label and no `aria-label`, so a screen
reader announced "combo box". Labelled. Guard: `test_every_dropdown_has_a_name_a_screen_reader_can_read`
(all six other dropdowns were already wrapped in a `<label>`).

## System-wide recheck
An independent sub-agent crawled every tab in both themes with Playwright (report filed in the
session; its one finding — the 500 above — is defect 136). Static sweeps added:
- every `<select>` has an accessible name (guard above);
- no `href="#"` dead links in the SPA;
- no table wider than a five-column budget (guard from round two);
- the reports page cannot regress to a bare navigation.

## Deliberately not built, with the reason
**Multi-step sequences** (the sixth audit gap): a sequence needs durable scheduling, a stop
condition per step (replied / booked / unsubscribed), a per-recipient cursor and a suppression
list — it is a background engine, not a page. Building it badly would send duplicate messages to
real customers, which is worse than not having it. It is recorded as the top outstanding CRM item
in `HANDOFF.md` with what it needs.
