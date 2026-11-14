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

## Part two: what the independent crawl found, and what was done about it

An independent sub-agent walked all 16 tabs in both themes with Playwright, exercised safe
controls, collected every `a[href]`, measured overflow, and drove the ⌘K palette from six pages.
Its own scope note: no writes, no sends, no deletes. It found **five real defects**, all fixed here.

| # | Severity | Defect | Cause | Fix |
| --- | --- | --- | --- | --- |
| 141 | HIGH | ⌘K palette could navigate to a row that was not on screen | 9 rows drawn (`slice(0, 9)`), arrow keys allowed all 16 matches; the 9th ArrowDown moved the highlight off the rendered list, and Enter then went to an unseen page | a moving window keeps the highlight in view, plus "n–m of N" |
| 142 | MEDIUM | A search with no hits claimed the business had no data | both empty states keyed off the *filtered* list, so "No enquiries yet — that is normal on day one" and "No contacts yet" appeared over real rows | "No enquiries/contacts match \"x\"" with a "clear the search" line; day-one copy only when nothing is filtered |
| 143 | MEDIUM | The New quotation card clipped its line row | a fixed 3-column grid inside a 360px card: scrollWidth 665, `overflow-x: clip`, so the **Unit price** box was outside the card and untouchable | the three fields wrap and each keeps its label |
| 144 | MEDIUM | A company could only be deleted | the row menu had one item, and rows had no open/edit path | Open button plus an editor with a save, and "Edit these details" in the menu |
| 145 | LOW | Setup said "Five short steps" and showed three | copy outlived the wizard's shape | "Three short steps" |

Live verification after deploying: palette reports "5–13 of 16" with the highlight on a rendered
row ("Settings · Permissions"); Enquiries shows `No enquiries match "zzzz"` and no day-one claim;
the quote card is 358px inside 360px with the unit-price box visible and reachable; Companies has
Open buttons and an editable dialog with a save; Setup reads "Three short steps". Zero page errors.

Mutation-proofs, each watched red then restored: the fixed slice again for #141, the day-one copy
for #142, the clipping grid for #143, a menu without the edit item for #144, "Five short steps"
for #145.

## Also fixed from the crawl's layout evidence
Products, Quotes, Contacts and Companies tables were wider than their panel (Products 2080px in
1168px) and only reachable by sideways scrolling. Each was trimmed by folding secondary facts
into the primary cell (unit + status into Product, paid + status into one cell, channel + message
count into one, people + open deals into one) and moving stacked buttons behind a `MoreMenu`;
Products' stock adjuster became a dialog. Now: Enquiries 1112, Contacts 1112, Companies 1112,
Quotes 1112, Products 1112 — all inside a 1168px panel, with a test that fails if any table grows
past its column budget.

## What the crawl cleared (no action)
- Every one of the 16 tabs renders in both themes with zero console errors and zero 4xx.
- Only four `a[href]` exist in the app; `/privacy` and `/guide/bonsai-cladding` are 200,
  bonsaibim.org is 200, blender.org answers 403 to automation only (bot protection).
- No `href="#"`, no empty hrefs, no cross-host surprises beyond those two vendor links.
- Contacts "Open", Calendar connect, density toggles and the Social view switch all work.
- `/null` appearing as a stray tab in one media run was the crawl's own instrumentation; a clean
  re-run opened one blob URL. Not reproducible, nothing changed.

## Known, judged, and left alone (recorded, not silently dropped)
- **Browser Back leaves the Studio** rather than returning to the previous tab: navigation is
  buttons, not routes, and the URL stays `/studio`. Making it real needs the router rework that
  the SPA deliberately avoids; it is listed in the handoff as a design decision to revisit.
- The sidebar scrolls at 900px height to reach the last two items (16 items). Works, worth a
  look if the product grows again.
