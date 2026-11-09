# Rust port status (`concierge-core`)

Rule: the Python in `api/app` stays deployed and untouched until a Rust module has passed parity and been
deliberately wired in and redeployed. Nothing here has been deployed.

Parity method: `parity/gen_vectors.py` (batch 1) and `parity/gen_vectors2.py` (batch 2) and `parity/gen_vectors3.py` (batch 3), `parity/gen_vectors4.py` (batch 4), `parity/gen_vectors5.py` (batch 5), `parity/gen_vectors6.py` (batch 6), `parity/gen_vectors7.py` (batch 7), `parity/gen_vectors8.py` + `parity/gen_ip_tables.py` (batch 8), `parity/gen_vectors9.py` (batch 9), `parity/gen_vectors10.py` (batch 10), `parity/gen_vectors11.py` (batch 11) and `parity/gen_tool_specs.py` run the live Python modules and writes `parity/vectors.json`;
`tests/parity.rs`, `parity2.rs`, `parity3.rs`, `parity4.rs`, `parity5.rs`, `parity6.rs`, `parity7.rs`, `parity8.rs`, `parity9.rs`, `parity10.rs` and `parity11.rs` must reproduce every vector. Run `cargo test` in this directory.

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
| tools.py: tool specs, chat/voice lists, `_capture_lead` input rules, knowledge query clamp | tools (+ generated `tool_specs.json`) | ported, 400 capture vectors captured from the live function via a fake DB pool; specs generated from Python, not retyped |
| events.py: Twenty payload, bridge-URL rule, delivery id, `lead_view`, `appointment_view` | events | ported, 300 payload + 21 URL + 80 view vectors. The delivery-id vectors mirror the inline expression in `process_twenty_once` (it is not a callable function), so that one pins the algorithm rather than calling live code |
| automation.py: owner alert wording, booking confirmation/reminder plan, review request, cancel rule | automation | ported; vectors come from running the real async `on_appointment_booked`, `on_appointment_status` and `on_lead_created` with a fixed clock and a fake queue (220 + 880 + 150 cases) |
| campaigns.py: template validation (CPython formatter grammar), render, email footer, mask, send_times, clean_filters, readiness | campaigns | ported, 50 templates (128 renders match; 40 conversion/format-spec forms are `Unsupported`, which makes no claim and is counted), 65 send_times, 62 filter, 64 readiness cases |
| owner_notifications.py `sms_body` | owner_notifications | ported, 160 vectors |
| voice_records.py `digest`, `audio_type` (container checks and WAV header rules as read by Python's `wave`) | voice_records | ported, 33 vectors incl. 14 WAV variants |
| calendar_connection.py `sync_one` control flow, `busy`, `event_id`, path quoting | calendar | ported as a state machine over an `Api` trait; 900 scenarios run the real `sync_one` against a scripted provider and the Rust version must make the identical request sequence (method, path, params, JSON body) and reach the identical stored state |
| sales.py: `effective_value`, `forecast` (banker's rounding on the weighted total), `_money`, `digest_text`, `digest_is_due` | sales | ported, 200 forecast + 27 money + 40 digest + 168 schedule vectors |
| tasks.py: `default_follow_up_due` (wall-clock 9am, DST-checked), `clean_title` | tasks | ported, 614 due-date + 10 title vectors |
| convo.py: `clean_utm`, `clean_session` | convo | ported, 133 vectors |
| owner_auth.py: `digest`, `password_hash`, `verify_password`, `clean_email` | owner_auth | ported; the real `password_hash` is run with a fixed salt, so hashes are byte-identical and Rust verifies Python-made hashes (PBKDF2-HMAC-SHA256, 600,000 rounds) |
| public_fetch.py: public-address rule (`ipaddress.is_global`, incl. IPv4-mapped IPv6) and the same-site HTTPS URL rule | public_fetch (+ generated `ip_tables.json`) | ported, 1,353 address vectors (every special-purpose network boundary + random) and 159 URL vectors; redirect resolution (`urljoin`) and DNS lookup are not ported |
| sms.py: Twilio and Android-gateway webhook signatures, gateway payload, `sender_ready` | sms | ported, 73 + 193 + 48 + 228 vectors (incl. the exact 300-second tolerance boundary) |
| rag.py: `tag_url` (UTM tagging via urlsplit/parse_qsl/urlencode semantics) and `build_system_prompt` for chat, SMS and voice | rag | ported, 100 URL + 160 prompt vectors; the prompt is compared character for character with a fixed clock |
| cloudflare_inbound.py webhook authentication (HMAC, replay window, size, payload shape), inbound_email.py ingestion rules and keys, enquiries.py keys and owner notice, email_drafts `_address`/`_subject` | inbound | ported; 61 scenarios run the real `handle()` with a fake database and clock (503/401/413/400/404/403 and 14 accepted cases with every stored value compared) |
| phone_sip.py SIP webhook verification (Standard-Webhooks style) and caller-number parsing; phone_relay.py TwiML, URLs, relay signature, id/consent patterns; managed_phone `sip_twiml`; mobile_connections `forwarding_steps`; tenants `slugify` | telephony | ported, 92 + 23 + 48 + 30 + 23 + 22 vectors incl. the exact 300-second boundary and Python's exception ordering on a non-ASCII signature part |
| voice.py `build_session` (Grok session config incl. the full voice prompt and tool list) and `_extract_token` | voice_session | ported; 60 sessions compared whole |
| evals.py behaviour checks | evals | ported, 140 combinations; failure messages that embed a Python `repr()` (prices, quoted replies) are compared by result and fixed prefix only |
| Twenty delivery outcome classification, calendar_connection OAuth/token handling, async DB/HTTP workers, rest of booking/outbox/quotations I/O, main (HTTP) | not started | next batches |

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

Python behaviours reproduced deliberately: `lead_view` raises on non-JSON `utm` text (so does the port); `_capture_lead` stores `""` for an invalid email. Arguments that are lists or floats are refused by the Rust normaliser rather than guessed. Datetimes passed to `twenty_bridge_payload` must already be Python `str()` text.

`verify_password` differs from Python only for stored strings that use `_` in the rounds field or whitespace inside the hex fields (Python's `int()`/`bytes.fromhex` accept them; this port rejects them, so it can only refuse a hash Python would accept, never the reverse).

**SSRF tables are Python-version specific.** `src/ip_tables.json` records the interpreter it came from and the test refuses to run if the vectors came from a different one. CPython adds ranges in patch releases (3.13.18 here includes `3fff::/20`), so regenerate both files with the interpreter that runs production before relying on this module. Scope-id IPv6 (`fe80::1%eth0`) and other forms Rust's parser rejects are treated as *not public*.

Signature checks: a signature containing non-ASCII text makes Python's `compare_digest` raise; here it simply fails verification. A gateway timestamp using `_` separators (accepted by Python's `int()`) is refused.

Webhook timestamps with non-ASCII decimal digits: Python accepts them as decimals and answers 'Expired signature'; this port refuses them as 'Invalid signature'. Same status (401), fail closed.

Telephony divergences (all fail closed): a SIP/webhook timestamp written with underscores is refused (Python accepts); caller numbers whose digits after the first are non-ASCII Unicode digits yield no number (Python returns one); `valid_websocket_signature` on a non-HTTPS base returns false where Python raises.

## Batch 12 (9 November 2026)

Rust `device_sms` ports token hashing, bearer/tenant authentication decisions, enqueue validation and repeated-job outcomes, receipt/inbound validation and operational keywords. Rust `pbx` ports explicit route validation, AudioSocket headers/encoding and the consent-started recording mixer. Database transactions, receipt persistence, media transport and HTTP handlers remain in Python. Golden vectors are generated by `parity/gen_vectors12.py` from the real Python functions with fake database/clock/transport boundaries; no messages are sent.

Vector counts: auth: 70, enqueue: 252, routes: 23, recordings: 88, receipts: 80, packets: 20, incoming: 72, hashes: 4, keywords: 13. Eight tests compare these outputs. Deliberate fail-closed differences: non-ASCII decimal digits in phone numbers are refused; receipt UUIDs must be canonical hyphenated text (Python also accepts compact, URN and braced forms). Route ports must be JSON integers; Python also compares floats/bools.

## Batch 13 (9 November 2026)

Ported from the live Python, with vectors from `parity/gen_vectors13.py` (fake databases, no network, nothing sent):

| Python | Rust | Evidence |
|---|---|---|
| channel_authorization.py: `ChannelAuthorization` validation (pydantic lax bools, literals), acknowledgement guard, channel allow-list, `readiness` | channel_auth (+ pydantic) | request validation incl. every pydantic bool spelling, readiness (120), membership, guard |
| owner_knowledge.py: `BusinessDocument`, `casefold` identity, document-id rule | knowledge (+ generated `casefold_table.json`) | validation cases incl. 100 KB / multi-byte limits, identity cases, id cases |
| managed_phone.py `PhoneSetup`, mobile_connections.py `MobileConnection` | phone_setup | field-by-field error types, extra-key rejection, E.164 pattern |
| owner_maintenance.py batch-size guard, table list | maintenance | 18 cases |
| acknowledgements.py full decision flow (decline, confirm, authorize, lead, outbox) | acknowledgements | about 2,450 scenarios run the real `request()` against a recording fake database; result and ordered effects must match |
| ingest.py `_store` record building and transaction, demo-question prompt and parser; embeddings `to_pgvector` | ingest, pyjson | 28 store scenarios (incl. short embeddings: nothing written), 60 question cases, 320 vector texts |

Deliberate differences (all fail closed or are declared `Unsupported`, never silently different): a `recipient` argument that is a float, list or
dict returns `Unsupported` (Python would use its `repr`); `json.dumps` of floats is not reproduced; non-ASCII decimal digits in phone numbers are
not treated as digits. `casefold_table.json` is specific to the recorded CPython and Unicode versions; regenerate it with the production interpreter.
Fourteen temporary mutations (inverted guard, wrong case folding, wrong operation order, wrong limits, wrong rounding and others) were each caught by
a failing test and then restored.

## Batch 14 (9 November 2026): the crawler

Vectors from `parity/gen_vectors14.py`, which runs the live `app.crawler` plus CPython's `urllib.parse`, `html.parser` and `urllib.robotparser` with a fake
network (no sockets) and a deterministic stand-in for trafilatura.

| Python | Rust | Evidence |
|---|---|---|
| urllib.parse `urlsplit`/`urlparse`/`urlunsplit`/`urljoin`/`urldefrag`/`hostname` as used by the crawler | pyurl | about 13,000 URL cases: normalize (5,200), urljoin (2,600), urldefrag, host_of |
| crawler `normalize`, `host_of`, `extract_links` | crawler | link extraction on about 2,000 HTML snippets (comments, doctype, CDATA, PI, script/style/title/textarea modes, broken tags, entity decoding in attributes); the raw start-tag stream is compared too |
| html.parser tokenizer rules for CPython 3.13.18 (incl. the data it deliberately never reaches without `close()`) | crawler (`start_tags`) | patterns are transliterated verbatim with `fancy-regex` (lookbehind/lookahead) |
| urllib.robotparser (RFC 9309 version): grouping, longest match, Allow wins ties, `*`/`$`, percent-normalisation | robots | 500 generated robots.txt files, about 9,600 decisions (645+ denials), plus a normalisation table |
| crawler `_sitemap_urls`, `_load_robots`, `_fetch`, `crawl` loop | crawler | 150 sitemap scenarios, 169 fetch cases, 166 whole crawls incl. exact request sequence and the `max_pages*10` frontier guard |

Not ported (declared, never guessed): trafilatura text/metadata extraction (`extract_page`), the real HTTP transport and DNS, and the async
scheduling. Declined cases (`Fail::Unsupported`): netlocs with non-ASCII characters (CPython applies NFKC) and IPv6 zone ids; both are counted in the test
(about 2% of the corpus, which over-samples them). `html_tables.json` (entity table) is specific to the recorded CPython; regenerate with the production
interpreter. Fifteen mutations were caught; one more (atomic lazy groups in robots patterns) is a proven equivalent mutant (the leftmost match is always the best
choice for the remainder), and three mutants first survived and exposed real test gaps, which now have dedicated vectors.

## Batch 15 (9 November 2026)

Vectors from `parity/gen_vectors15.py` (live `config`, `owner_onboarding`, `email_drafts`, `tenants`; fake databases and a fake model; nothing sent).

| Python | Rust | Evidence |
|---|---|---|
| config.py owner-portal validator, `effective_llm_key`, `voice_ws_url`, `sms_configured`, `email_configured` | settings | 31 portal URLs (incl. credentials, query, fragment, loopback HTTP) and 400 generated settings |
| owner_onboarding.py `OwnerBusinessProfile` (11 fields, pydantic int/bool/dict/str rules, opening-hours rules, URL/email/phone/timezone rules), `website_channel_status` | owner_profile | about 680 profiles with exact pydantic error type and location; every one of the 598 IANA zones known to Python must be accepted |
| email_drafts.py address/subject cleaning, drafting prompt, stored draft parameters, approval decision | drafts | 60 drafting prompts compared character for character, 120 draft inserts, 24 approval paths with the exact queued row |
| tenants.py updatable fields, UPDATE statement, slug conflict sequence, create parameters, clone snapshot, public view, JSON column loading | tenants | 220 updates (SQL text and parameters), 24 creates with 0-5 slug conflicts, 40 clones |

Documented differences: timezone check uses chrono-tz plus tzdata's `Factory`; host-specific files Python accepts as zones (`localtime`, `posixrules`) are
refused. Integer text beyond 128 bits and non-JSON-repr floats return `Unsupported`. Equivalent mutants (cannot be killed because the code is redundant in
Python too): the 7-weekday-key count (more than 7 keys always contains an invalid day name) and the CR/LF check in `_address` (the e-mail pattern already refuses them).

## Batch 16 (9 November 2026): one conversation turn

`chat.rs` ports `chat.run_turn` (web chat, SMS and email): history, system prompt assembly (with the already-ported prompt builder), the tool-call loop
(four rounds maximum, bad JSON arguments become `{}`), the quote guard with its single corrected retry and fallback, the generic failure text, conversation
storage and the queued owner notice (never sent here, never queued on dry runs). All effects go through an `Env` trait. 260 scenarios run the real
`run_turn` with a scripted model and scripted tools; the Rust version must produce the same result and the same ordered list of effects (every model request,
tool call with its context, storage write and notice). Twelve mutations were caught; two survivors are equivalent (empty replies never contain amounts; an empty
tool-argument string is invalid JSON and becomes `{}` either way).
