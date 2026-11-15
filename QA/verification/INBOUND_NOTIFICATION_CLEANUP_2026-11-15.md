# Inbound mail arrived as a stylesheet — 2026-11-15

Jo forwarded a notification our own platform had sent him at 13:14:

```
Channel: email
Email: sa@ahrefs.com

(Trendibizz) Page has links to redirect [New]: 39 URLs
/* -------------------------------------
RESPONSIVE AND MOBILE FRIENDLY STYLES
------------------------------------- */
:root { color-scheme: light only; }
...
Health Score 100 =C2=B7 Errors 0 =C2=B7 Warnings 44 (+40)
```

## What that email was

Not a customer. It is an **Ahrefs Site Audit digest** for trendibizz.com that was routed to
admin@trendibizz.com, picked up by the inbound email channel, stored as an enquiry, and re-sent to
the owner in our notification template. Health score 100, 0 errors — a good report, delivered as
several hundred lines of CSS.

## Two defects

1. **The body was not text.** The Cloudflare Worker's HTML fallback strips tags but leaves the
   *contents* of `<style>`, the quoted-printable escapes (`=C2=B7`, `=3D`, `=name` soft breaks) and
   the blank-line padding. Our API then stored and mailed that verbatim.
2. **An automated message was presented as a customer enquiry.** The `automated_sender` flag was
   already being computed (List-Id / Auto-Submitted / Precedence) but nothing used it in the
   enquiry text.

## Fix

- New `api/app/inbound_text.py: clean_inbound_text()` — decodes quoted-printable only when escapes
  are actually present, removes `<style>/<script>/<head>/<title>` blocks (including a block left
  open by a truncated provider), strips tags and entities, drops stylesheet leftovers (multi-line
  comments, `selector {`, `prop: value;`, one-line rules), collapses blank lines, caps at 20,000.
  It only ever removes; it never interprets or adds words. Ordinary mail is returned byte-identical
  (guarded).
- Applied at ingest (`cloudflare_inbound.handle`, so the draft, the enquiry and the notification all
  get clean text) and again in `inbound_email.ingest_verified` as defence in depth for an older
  Worker.
- Automated senders now open with `(Automated message — not a customer enquiry.)`.

## Proof

- Unit: `api/tests/test_inbound_text_cleaning.py`, 8 guards including the real Ahrefs body.
  Mutations that turn them red: deleting the stylesheet-comment strip (2 fail) and replacing the
  ingest call with a passthrough (the wiring guard fails).
- Live end-to-end: a signed replay of the same shape through `POST /api/v1/inbound/cloudflare` on
  the production box returned `{"accepted":true,"draft_id":103}`, and the stored draft read
  `New crawl for Trendibizz / 47 internal URLs were analyzed. Health Score 100 · Errors 0 · Warnings 44`
  with flags `["unverified_sender","spam_high","automated_sender"]`. The enquiry text carried the
  automated prefix. The replay rows were deleted afterwards.
- Suite: **1214 passed, 36 skipped**.

## Still open (external)

The Worker's own HTML fallback still emits stylesheet text (it is deployed on Cloudflare, not from
this repo). The API now cleans every message regardless, so this is a belt-and-braces item, not a
live defect.

**Lesson recorded for our tooling:** never verify an inbound-mail fix by replaying through the
production endpoint — it mails the owner. Verify `classify()` and `clean_inbound_text()` directly,
and use the test suite for the rest. Anything that must be end-to-end goes to a test tenant flagged
`is_test`, never to a live tenant's owner address.

## Second round: why it kept arriving, and the real gap

Two more notifications reached the owner at 13:19 and 13:21. **Both were mine.** To prove the
cleaning end-to-end I replayed a signed synthetic crawl message through
`POST /api/v1/inbound/cloudflare`; the first delivery was the enquiry notification, the second the
alert channel escalating ("Sent by email because the text message could not be confirmed"). That
was a mistake in method: the replay exercised the *send* path, not just the parse path. The replay
drafts, leads and queued outbox rows have been deleted/cancelled, and no further replays were run.

It exposed a genuine second defect, though. `automated_mail.classify("sa@ahrefs.com",
"Page has links to redirect [New]: 39 URLs")` returned **None**: Ahrefs signs crawl reports from
`sa@ahrefs.com` and — measured on the live box — that mail carries no `List-Id`, so the header
checks never fired. The enquiry and the alert were therefore correct behaviour for the classifier as
written, which is the bug.

**Fixed** (`app/automated_mail.py`):

- SEO and monitoring domains — `ahrefs.com`, `semrush.com`, `moz.com`, `majestic.com`,
  `screamingfrog.co.uk`, `sitebulb.com`, `uptimerobot.com`, `pingdom.com`, `statuspage.io`,
  `sentry.io`, `datadoghq.com`, `newrelic.com`.
- Machine local parts — `sa`, `news`, `newsletter`, `digest`, `updates`, `promo`, `promotions`,
  `marketing`, `reports`, `report`, `seo` (exact or followed by a separator, so `sam@` is a person).
- Scheduled-report subjects — `new crawl`, `site audit`, `crawl completed`, `your weekly report`,
  `site health`.

A classified-automated message now produces **no lead, no acknowledgement, no secretary job and no
owner alert** — that gate already existed and is now actually reachable for this mail.

Proof, without sending anything: on the live container,
`classify('sa@ahrefs.com', 'Page has links to redirect [New]: 39 URLs') -> 'localpart:sa'` and
`classify('sam@smallbuilders.co.nz', 'Quote please') -> None`. Guards in
`api/tests/test_automated_mail.py` (26 tests); mutation removing the Ahrefs domain turns one red.
Suite **1240 passed, 36 skipped**.
