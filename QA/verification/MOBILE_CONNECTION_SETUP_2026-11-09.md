# Business-specific mobile forwarding setup — 9 November 2026

Production setup flow deployed; actual carrier ingress is not activated.

Each business keeps its public mobile number, carrier, owner message destination,
knowledge and Grok context. The forwarding destination is separately assigned to
that business. Carrier instructions default to generic; Spark codes require an
explicit per-business spark_nz selection. Neither country prefix nor another
customer's carrier supplies a default. Exact assigned ingress destinations avoid
relying on forwarding carriers preserving the original dialed mobile number.

Deployed source: api/app/main.py, schema.sql, managed_phone.py,
mobile_connections.py and api/static/owner.html. API container trendi-api-1 is
healthy, image sha256:9abe3bb2af79f6f7c7fa4b1171f99ebeae1aa7bc8c18b36d1b8737296aade212.
Public owner-ui contains the new setup. Private healthz returns ok;
public unauthenticated owner mobile-connection returns 401. Admin routes remain
hidden at the public gateway. No business route or forwarding was activated.

Validation: full API suite 124 passed; mobile connection focused suite 5 passed;
16 mocked browser owner/viewer checks passed; owner JavaScript syntax and git
diff whitespace checks passed. Browser checks cover own destination, owner-only
codes, no false connected status, and logout clearing. No physical handset test.

Rollback source archive on VPS:
/opt/trendi/backups/mobile-setup-20261109/source-before.tgz
Rollback image: trendi-concierge-api:before-mobile-setup-20261109
Build log: /opt/trendi/backups/mobile-setup-20261109/build.log

Asterisk bridge remains local, independently verified with real Asterisk and
live Grok using synthetic calls; see ASTERISK_GROK_VERIFICATION_2026-11-09.md.
The bridge currently saves transcripts, not telephone audio recordings.
Owner SMS queued does not mean delivered. Existing native SMS confirmation
remains required. No automatic outbound callback or caller-ID spoofing claimed.

Remaining acceptance: provision a real per-business carrier ingress destination
under authorized existing/free services, configure the corresponding SIP route,
forward the actual mobile, verify Grok and correct business CRM, then verify
owner receipt. Recording consent/capture for telephone audio remains unfinished.
No carrier account, credit, number purchase, terms acceptance, phone forwarding,
external call or message was executed. 2talk free-plan signup was inspected but
not submitted; its terms require credit, so free software is not proof of free
carrier transport. Task browser tab closed. No universal carrier coverage claim.
