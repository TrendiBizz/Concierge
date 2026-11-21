# N3 AI / voice outage resilience (2026-11-21)

**Cause:** `llm.py` used one provider with SDK-default retries and no fallback; a vendor outage meant chat 502s.
Failed AI voice calls ended `failed` with the caller left in silence.
**Fix:** `llm.py` retries transient errors with backoff, opens a circuit breaker, and fails over to an optional
OpenAI-compatible secondary (LLM_FALLBACK_*; off unless all three set). Streams fail over only before the first
chunk. 400/422 never fail over. Voice: `render_routes.py --voicemail-dir` adds ring-owner + greeting + Record after
AudioSocket returns; `voicemail_fallback.py` ingests the spool (CRM enquiry, stored recording, owner alert via paired phone).
**Proof:** tests/test_llm_failover.py (8), tests/test_voicemail_fallback.py (8); full suite 1650 passed, 42 skipped.
Mutation checks: disabling failover classification failed 6/8; disabling the voicemail option failed the unchanged-dialplan test.
**Not verified:** no live secondary provider (no key), no real Asterisk fallback call (spool mount and greeting not installed).
