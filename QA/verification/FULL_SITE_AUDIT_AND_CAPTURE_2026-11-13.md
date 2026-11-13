# Full site audit, capture from the customer, and teams everywhere — 2026-11-13

Three asks: click through the whole site, put teams wherever several people can be, and stop relying
on the owner to type addresses when the customer's own call or email tells us.

## 1. The audit

**Public website — 47 pages crawled, every internal link followed: 0 failures.** Every page and
asset answered 200.

**Studio — all 14 tabs, in a real signed-in session:**

```
tab                h1                     renders  errors
Home               —                      yes      0
Setup              —                      yes      0
Permissions        —                      yes      0
Team               Team                   yes      0
Your CRM           Your own CRM           yes      0
Enquiries / Contacts / Bookings / Quotes / Products / Reports / Social /
Marketing media / Designs                     yes      0
```

No page errors, no 5xx, no "Could not load" state on any tab. Then the flows themselves were driven
end to end in the browser: team role change, remove and restore access; export download; contact
open; address add and remove; operator-console team controls. Every one worked, 0 JS errors.

Honest scope note: this proves every page loads and the flows above work. It does not re-click every
content button on every tab (social composer, media upload, quote builder) — those are covered by
their own tests from earlier sessions, and are listed as the remaining click-through in the handoff
rather than claimed as done here.

## 2. Capture the customer's own identifiers

**Caller ID was being thrown away on both self-hosted voice paths.** The AudioSocket bridge receives
only a call UUID — no number — and recorded `from_number` as an empty string, so every PBX call
created a customer nobody could find again. Mid-call turns on the streaming path also recorded no
number even though the call record held it. Both now resolve the caller: the bridge asks Asterisk
(`Status` over AMI, matched by channel unique id), the streaming path reads `phone_calls`.

The bridge test then caught a second bug in my own fix: I required E.164 with a leading `+`, but
Asterisk reports national numbers such as `0215551234`, so every real caller ID would still have been
rejected. It now accepts the digits and lets the usual normaliser apply the business's country code.

**Every address now records where it came from**, and the portal says so:

| source | shown to the owner |
|---|---|
| `phone` / `voice` | captured from a call |
| `email` | captured from an email |
| `sms` | captured from a text |
| `chat` | given in a chat |
| `owner` | added by you |
| `import` | from your import |
| `backfill` | from your existing records |

That is the answer to "the address field issue": the field no longer asserts anything you cannot
check. An address the customer gave us is labelled as captured; one that was typed is labelled as
yours. Nothing is silently trusted, and nothing automatic is silently discarded.

## 3. Teams wherever several people can be

| surface | before | now |
|---|---|---|
| Studio | Team tab (built earlier today) | listed, role change, invite, remove/restore |
| Operator console (`owner-ui`) | invite only — **no way to see or revoke** | team list, role change, remove/restore access |

The operator console was the remaining gap: it could invite staff and never revoke them. It now
shows the whole team with role selects and a Remove-access button that ends the session immediately.

## Proof

* `api/tests/test_capture_source.py` — 4 tests: each channel names itself as the source; caller ID is
  read from Asterisk; an unmatched or junk number is never attached; no AMI settings means no guess.
* `api/tests/test_customer_addresses.py` — +1: an imported address records `import`.
* Full suite **1017 passed** against a real Postgres; every fix mutation-checked (removing the AMI
  lookup fails the caller-ID test; the `+`-only regex was caught by the same test before shipping).
* Browser, production: console team panel lists members, marks you, changes a role, removes access,
  offers restore, restores — 0 JS errors.

Test data (one contact, one spare user) deleted afterwards; the review workspace is back to empty.

## 4. The rest of CRM capture, exercised against production (2026-11-13, evening)

Not unit tests — signed requests to the live API, tenant `trendi-meta-review`, replies held off.

| channel | what happened | result |
|---|---|---|
| Email | signed Cloudflare inbound payload to the tenant's registered mailbox | **captured**: case `email:capture.email@portability.test`, address source `email` |
| Chat | `capture_lead` with an email | **was broken, now captured**: case created, address source `chat`, lead stamped with `case_id` |
| Voice / caller ID | real calls, operator-confirmed | working; bridge AMI + stream paths covered by unit tests |
| SMS | provider reports **none**; no Twilio token on the box | **cannot be exercised — not configured** |
| Missed call | telephone receptionist disabled for the review tenant; no enabled numbers | **cannot be exercised — not configured** |

Two of these are config, not code: SMS has no provider at all in production, and the missed-call
recovery needs the receptionist enabled on a tenant with an active number. Both are recorded as open
items; neither is claimed as verified.

### Bug found by doing it: chat leads were never customers

`tools._capture_lead` wrote a `leads` row and stopped. A visitor who gave their email in the chat
became a lead with no customer case and no address — so when they emailed a week later they arrived
as a stranger with a second history. It now reconciles the customer first (`source="chat"`) and
stamps `leads.case_id`. Proven live: `lead -> customer {'case_key': 'email:chat.capture@portability.test',
'source': 'chat'}` and unit-tested with a mutation check.

### Operational note

My chat probes sent five owner-alert emails to admin@trendibizz.com ("Chat enquiry for Trendi").
Owner alerts are deliberately exempt from a paused tenant, so the hold did not stop them. Subsequent
runs muted `notify_email`/`notify_phone` and restored them afterwards. Test rows (5 email drafts,
leads, cases) deleted; the review workspace is back to empty.

## 5. Per-button click-through (all 14 tabs)

Every visible control on every tab, clicked where it does not send, publish, delete or pay; Escape
after each; JS errors and 5xx recorded.

```
tab               controls  clicked  skipped  problems
Home              1         0        1        none
Setup             2         0        2        none
Permissions       3         0        3        none
Team              3         1        2        none
Your CRM          5         2        3        none
Enquiries         2         0        2        none
Contacts          1         0        1        none
Bookings          3         0        3        none
Quotes            5         2        3        none
Products          2         1        1        none
Reports           1         0        1        none
Social            11        1        10       none
Marketing media   7         3        4        none
Designs           2         0        2        none
```

**9 controls clicked, 0 failures, 0 JS errors, 0 5xx.** The honest reading is that the review
workspace is empty: most screens only grow their controls once there are products, bookings and
quotes in them, so this pass proved the empty states are sound rather than exercised the editing
flows. A seeded pass — create a product, a booking and a quote through the screens, then click
everything again — is the next action, not a claim made here.
