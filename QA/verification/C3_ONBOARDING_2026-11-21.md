# C3 — Self-serve onboarding and activation showstoppers (2026-11-21)

| # | Cause | Fix | Proof |
|---|---|---|---|
| 1 | Studio had no knowledge-base screen; new tenants had 0 chunks | `web/portal/src/Knowledge.tsx` (read website, add/remove notes) as Studio tab "What Concierge knows"; invite email points to it | `test_studio_has_knowledge_and_privacy_tabs_...`; Studio build + lint |
| 2 | `ownership()` required `password_hash <> ''`; Stripe-provisioned owners have `''` (Studio is passwordless) | dropped the clause in `channel_authorization.ownership` | `test_provisioned_owner_with_empty_password_hash_...` (mutation: re-adding clause turns it red) |
| 3 | Streaming chat checked takeover with `phone="", email=""`, which always returns False | `casetimeline.is_paused_for_session` (conversation -> lead -> case); used in `run_turn_stream` and `run_turn`; visitor message still saved/captured | `test_takeover_is_found_from_the_chat_session...`, `test_streaming_chat_stays_silent...` (mutation red) |
| 4 | No Studio UI for `/owner/privacy/*` | `web/portal/src/Privacy.tsx`: requests list with working-days counter and overdue flag, confirmed Erase, consent record/lookup | static test + Studio build |
| 5 | `on_appointment_booked` only ran when calendar state was `synced` | `calendar_connection.NOTICE_READY` also accepts `unconnected`, `needs_contact`, or attempts >= 10 | `test_appointment_notices_go_out_without_a_connected_calendar` (mutation red) |

Also fixed: `owner_invites.py` told owners to open a non-existent "Business" tab.
