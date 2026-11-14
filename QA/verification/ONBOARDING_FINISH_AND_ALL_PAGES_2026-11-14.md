# Finishing onboarding must not require granting every permission

Reported before a reinstall test: on the Permissions screen a customer may grant some, one, or
none of the capabilities — and **they still need the confetti when they press Continue**.

## What was wrong

The celebration fired only when `CHANNELS.every(...)` was authorised. A business that says "no" to
receiving texts, or declines call recording — the common case for a busy tradesperson — finished
onboarding and got nothing. Worse, there was no explicit Continue on that screen at all: the only
way out was a different page's button.

## What it does now

* A **Continue** button at the foot of Permissions, inside an accent panel that says *"That is
  everything you have to decide now"* and *"Permissions are yours to change later — nothing here is
  permanent, and the chat window works whether or not you grant any of them."*
* Pressing it fires the confetti **unconditionally**, then moves them into the workspace. Some/all/
  none granted makes no difference.
* The earlier rule (celebrate once every channel has been *decided*) is kept as a second trigger,
  so the moment lands either way.
* The button reports itself: "Opening your workspace…" while it navigates.

## "The entire website fixed"

Every page now inherits the shell instead of pinning itself to a narrow column. Removed the last
`maxWidth: 1040 / margin: 0 auto` wrappers from Quotes, Contacts, Products, Designs, Social, Media,
Bookings, Reports and Team. Bare empty states became real ones carrying advice:

| Page | Before | Now |
|---|---|---|
| Products | "No products yet. Add your first item…" | "No products yet" + what the prices are actually used for |
| Enquiries | "No enquiries yet. Connected channels will capture them here." | "No enquiries yet — that is normal on day one" + what will land there |
| Quotes | "No quotations yet." | "No quotes yet" + send/open/accept explanation |
| Contacts | one long sentence | "No contacts yet" + merged repeat customers |
| Social | "No drafts yet." | nothing publishes until approved |
| Designs | "No enquiries yet…" | pick the job and measure it |

## Proof (live, ACME Ltd, 1600×1000)

| Check | Result |
|---|---|
| Quotes / Products / Bookings / Contacts / Reports / Team / Designs / Social / Media / Permissions | all render, **no horizontal overflow** |
| ACME's permissions reset for a clean reinstall | **0 authorised, 7 not authorised** |
| Continue pressed with **nothing** authorised | confetti canvas appears, then cleans up |
| Dark mode | readable (screenshot `studio-permissions-continue-2026-11-14.png`) |

Guards (`tests/test_studio_shell.py`, now 10): Continue must call `celebrate()`, must **not** depend
on `CHANNELS.every`, must carry `onDone`; no page may reintroduce a `maxWidth: 1040` wrapper; each
page must keep its `c-empty` state. Mutated the `celebrate()` call out of `finish()` and watched
`test_a_customer_who_grants_nothing_still_gets_the_celebration` go **red**. Suite **1163**.
