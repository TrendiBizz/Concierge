# Pause everything (per tenant) — 2026-11-13

The owner could not stop Concierge. The only kill switch was the operator's, which pauses the
**whole deployment** — so exposing it to a customer would have silenced every other business. This
adds a per-tenant switch, and shows it in the Studio at all times.

## What it does

`tenants.paused_at` / `paused_by`, toggled by the owner (`GET`/`POST /owner/pause`, owner role).
While it is on:

| Path | Behaviour | Why |
|---|---|---|
| Chat turn | No model call. Visits are answered "we have your message, someone will get back to you shortly" | A silence is worse than a holding line, and the visitor must not be left staring at nothing |
| Streaming chat | Same, via its own code path | It is a separate implementation; gating only `run_turn` would leave the widget answering |
| SMS / voice / email | Suppressed entirely, no reply produced | Replying *is* sending |
| Outbox (any customer send) | `skipped / tenant_paused` | Covers approved replies, campaigns and scheduled sends |
| Owner alerts | **Not** suppressed | A paused business still needs to know who tried to reach it |
| Inbound capture | **Still happens** | Pausing must never cost the owner a lead |

The read happens on every message (no cache), so a pause takes effect on the next one. It fails
**open** on a database error: a transient read fault must not silently silence every business.

## Live proof (production, scratch tenant `trendi-meta-review`)

```
signed in via link: True
initial pause state: 200 {'paused': False, 'since': None, 'by': None}
paused:              200 {'paused': True, 'since': '2026-11-13T02:15:44Z', 'by': 'meta-review@…'}
chat while paused -> status: 200
  reply: "Thanks — we have your message. Someone will get back to you shortly."
  is the holding line, not the model: True
resumed:             200 {'paused': False, 'since': None, 'by': None}
chat after resume -> status: 200
  answered by the model again: True
tenant left un-paused: True
```

Messages were still captured while paused: two `leads` rows exist for the tenant, one from the
paused turn and one from the resumed turn, each with its `enquiry_sources` row. (Those two rows are
the test's own traffic on the scratch tenant.)

## Tests — `api/tests/test_tenant_pause.py`, 15 passing

State read/write; the loaded-row fast path; fail-open on a read error; a suppressed turn carries
every key the chat endpoint reads; paused chat takes the message and says something humane; paused
SMS produces no reply; resume restores the normal path; a viewer cannot pause; the owner's email is
recorded; a queued customer email is skipped while paused; **owner alerts still go out**; nothing is
skipped when not paused; and the human-takeover shape regression (see the bug log).

Mutation checks performed: setting `tenant_off = False` fails the two paused-turn tests; restoring
the four-key takeover result fails the shape test.

## Deployed

API `sha256:ceb32…` → new image with `tenant_pause`; schema columns created on boot (verified in
`information_schema`); `GET`/`POST /owner/pause` answer 401 unauthenticated; social recreated and
attached; 0 tracebacks. Portal `assets/index-CZ6vMiU_.js` carries the switch.

**Not yet seen in a browser**: the strip renders from the served bundle; only a real click in
`/studio` confirms the layout, which stays on the setup walkthrough list.
