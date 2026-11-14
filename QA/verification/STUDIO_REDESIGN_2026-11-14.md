# The Studio was drab, and it was fighting the design system

The screenshot that started this: a narrow grey column in the middle of a wide screen, a flat list
of links with no grouping, no colour, and a footer link that read **"Privac"**.

## What was actually wrong

1. **The whole app was pinned to a narrow column.** A leftover rule from the Vite starter,
   `#root { width: 1126px; margin: 0 auto; text-align: center; border-inline: 1px solid }`, wrapped
   the entire product. That is also why the footer link was clipped: the brand line had nowhere to
   go. Removed — the shell owns the layout now, full width, left-aligned.
2. **Two guessed token names made the palette half-broken.** My first pass used `--color-bg` and
   `--color-text`, which this design system does not define (it uses `--color-background-body`,
   `--color-background-card`, `--color-background-surface`, `--color-text-primary`,
   `--color-text-secondary`). Result: a white page behind dark cards, with **white numbers on
   white**. Now wired to the real tokens, so the shell follows light and dark mode properly.
3. **There was no hierarchy.** Everything sat in one undifferentiated list.

## What it is now

* Gradient canvas, a brand tile with initials, sticky top bar, and a real sidebar.
* **Grouped navigation the way the tools our customers already compare us to group theirs** —
  GoHighLevel puts Dashboard / Conversations / Opportunities / Payments / Marketing / Reporting /
  Settings in its sidebar; [Jobber](https://help.getjobber.com/hc/en-us/articles/360033836333-Navigating-Jobber)
  and [Tradify](https://help.tradifyhq.com/hc/en-us/articles/360051120654--Tradify-s-Web-App-Full-Walkthrough)
  group by client → request → quote → job → invoice → schedule → reports. Ours now mirrors that
  job-to-cash shape:

  | Group | Items |
  |---|---|
  | Overview | Home |
  | Customers | Enquiries, Contacts, Bookings |
  | Sales | Quotes, Products, Designs and CAD |
  | Marketing | Social, Marketing media |
  | Insights | Reports |
  | Settings | Setup, Permissions, Team, Your CRM |

* A colour per group (violet, cyan, amber, pink, green, slate) carried through the group dot, the
  icon and the active pill, so which part of the business you are in is obvious at a glance.
* Hand-drawn SVG icon set (`icons.tsx`) instead of emoji, which rendered differently on every
  machine and could not be tinted.
* A hero line on every page that says what the page is for, KPI cards with an accent edge, and
  enquiry rows with an avatar and a status tag instead of a paragraph of dots.
* Empty states that encourage instead of shrugging: *"No enquiries yet — and that is normal on day
  one"* rather than "None booked." / "No open tasks."
* The greeting comes from the clock in Pacific/Auckland, not a hard-coded "good morning".

## The confetti

`celebrate.tsx` — a canvas burst, no dependency, 2.6s, removes its own canvas, and does nothing at
all under `prefers-reduced-motion` (a celebration must not make someone motion-sick on a job site).

It fires in two places:

* finishing setup (**"Open my workspace"**) — once per business, remembered in localStorage;
* the moment **every permission has been decided** on the Permissions page, whichever way they
  decided, because that is the real end of onboarding.

## Proof (live, production, ACME Ltd)

| Check | Result |
|---|---|
| Horizontal overflow at 1600×1000 | none (`scrollWidth <= innerWidth`) |
| Footer line | "Powered by Trendi · Privacy" — no clipping |
| Navigation groups rendered | OVERVIEW, CUSTOMERS, SALES, MARKETING, INSIGHTS, SETTINGS |
| Icons rendered | 14 |
| Confetti canvas appears on "Open my workspace" | **1** |
| Confetti cleans up afterwards | canvas count returns to **0** |
| Light mode legible | KPI numbers and hero text readable (screenshot) |
| Dark mode legible | screenshot |

Screenshots: `studio-shell-dark-2026-11-14.png`, `studio-shell-light-2026-11-14.png`,
`studio-confetti-2026-11-14.png`.

Guards: `api/tests/test_studio_shell.py` (7) — the width rule, the grouping, icons per item, the
confetti wiring, reduced-motion, and "setup completion must call celebrateOnce". Mutated the width
back to 1126px and watched `test_the_app_is_not_pinned_to_a_narrow_centred_column` go **red**.
Suite **1160**.
