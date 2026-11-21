# N6 integrations, API keys and complete webhooks (2026-11-21)

**Cause:** webhooks only emitted `customer.created`, had no retry worker, and there was no tenant API
key or connector to Xero / ServiceM8 / Microsoft 365 (report N6).

**Fix**
- Phase 1: `api_keys.py` (hashed, tenant-scoped, read-only `/api/v1/{contacts,enquiries,appointments,events}`,
  Studio endpoints `/owner/api-keys`); `portability.py` emits `customer.enquiry`, `quote.accepted`,
  `appointment.booked`, `call.completed`; exponential backoff (`next_attempt_at`, 8 attempts) with a
  60s background retry worker. SSRF guard already existed (`public_fetch`) and is unchanged.
- Phase 2/3: `integrations.py`: Xero OAuth (contact + draft invoice), Microsoft 365 OAuth (Outlook event
  on booking), ServiceM8 (customer's own API key: client + job). Tradify and Fergus are registered but
  disabled (partner API access). Every provider is disabled until credentials exist.

**Proof:** `api/tests/test_n6_integrations.py` (8 tests); mutation check (dropping the tenant filter
on `/api/v1/enquiries`) fails the isolation test; full suite 1686 passed.

**Not done:** customer self-serve reschedule/cancel links, true two-way Google Calendar sync, Studio UI
for keys/integrations (API only), real Tradify/Fergus connectors.

**Jo must supply:** Xero app client id/secret (`XERO_CLIENT_ID/SECRET`), Microsoft Entra app
(`MS_CLIENT_ID/SECRET`), Tradify/Fergus partner access; ServiceM8 needs nothing (each customer pastes their key).
