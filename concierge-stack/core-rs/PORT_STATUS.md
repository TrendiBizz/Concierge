# Rust port status (`concierge-core`)

Rule: the Python in `api/app` stays deployed and untouched until a Rust module has passed parity and been
deliberately wired in and redeployed. Nothing here has been deployed.

Parity method: `parity/gen_vectors.py` (batch 1) and `parity/gen_vectors2.py` (batch 2) and `parity/gen_vectors3.py` (batch 3) run the live Python modules and writes `parity/vectors.json`;
`tests/parity.rs`, `parity2.rs` and `parity3.rs` must reproduce every vector. Run `cargo test` in this directory.

| Python module | Rust module | Status |
|---|---|---|
| chunking.py | chunking | ported, 375 vectors match |
| guard.py (quote guard) | guard | ported, 300 vectors match |
| contact.py | contact | ported, 52 vectors match |
| unsub.py | unsub | ported, tokens byte-identical |
| ical.py | ical | ported, feed byte-identical |
| security.py RateLimiter | rate_limit | ported (unit test) |
| scoring.py (weights, validation, assess, labels, describe) | scoring | ported, 500 scoring + 26 validation vectors match |
| sla.py `_alert_text` | sla | ported, 60 vectors match |
| outbox.py `next_allowed_send` | schedule | ported, 1,128 vectors incl. DST transitions in 8 zones |
| booking.py `day_slots` | schedule | ported, 420 vectors incl. DST gaps/overlaps and a 30-minute-DST zone |
| quotations.py `calculate` + validation + status transitions | quotation | ported, 631 vectors match (81 exotic decimal forms such as `1e2`/`1_0` deliberately unsupported and counted, never silently passed) |
| automation.py `fmt_local` | schedule | ported, 747 vectors across 9 zones |
| booking.py local-time check, read-back, `booking_result` | schedule, booking_text | ported, 261 vectors |
| events, tools, calendar_connection, DB/I-O parts of booking/outbox/quotations, main (HTTP) | not started | next batches |

Known, documented differences: `\s` in the paragraph splitter follows Rust/Unicode White_Space semantics for the
chunker's regex-free splitter only where Python agrees (the vectors include U+2003, U+3000, U+00A0); phone digit
filtering uses ASCII digits only (Python `\D` also treats non-ASCII decimal digits as digits).

## Not fixable by code (needs a person or a provider)
1. Incoming SMS from another phone to the business number.
2. Human microphone conversation on the website.
3. Separate guest inbox receiving a calendar invitation (needs a second authorized address).
4. Real business hours (owner input) before public booking is enabled.
5. Google OAuth production verification (Google console action by the account owner).
6. Unattended SMS: the Mac requires a Send confirmation; a hosted SMS provider would be a purchase.

DST rule: a wall-clock time inside a spring-forward gap yields no slot; an ambiguous (fall-back) time uses its first occurrence, matching Python `zoneinfo` `fold=0`. `weights_for` ignores non-integer or unknown stored entries, where Python would carry them through.
