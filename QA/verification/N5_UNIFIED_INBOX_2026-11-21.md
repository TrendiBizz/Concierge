# N5 Unified inbox with live web-chat reply (2026-11-21)

**Cause.** Owners could read and reply to texts in Studio, but not to website chats. A chat visitor has no
phone or email, so "take over" depended on a lead and customer case existing (`casetimeline.is_paused_for_session`);
with no lead the AI kept answering. There was also no way for a human reply to reach the visitor's widget,
Studio's service worker had no `push` listener, and Products showed USD.

**Fix.**
- `conversations.owner_takeover_at` (schema): takeover stored on the conversation; `is_paused_for_session` honours it and still honours the case switch.
- `api/app/chat_inbox.py`: `/owner/chat/inbox`, `/conversations/{id}`, `/takeover`, `/reply` (idempotent on request_id, reply takes over), and public `GET /api/v1/chat/poll`.
- `api/static/widget.js`: polls for owner messages every 5 s while the panel is open; a suppressed (taken over) turn drops the typing dots and tells the visitor a team member will reply.
- Studio: one "Inbox" page with a Texts / Website chat switch (same read, take over, reply, hand back screen); `sw-v2.js` push + notificationclick listeners; Products currency NZD.

**Proof.** `tests/test_chat_inbox.py` (7 tests, 2 DB-backed). Mutation: removing `owner_takeover_at` from the pause check fails the takeover test; restored. Full pytest 1666 passed, 42 skipped. `tsc -b` and `vite build` clean.

**Not done (honest scope).** Email and phone/voicemail threads are not yet in the same Studio list; Studio has no "enable alerts" button (backend subscribe routes exist; owner-ui has one); Knowledge/voice playback/invoices/ICS/privacy/lead-scoring parity, the 5 hidden top tabs, Engage segmented control, local fetch wrappers (7 files), CrmQuotes inline buttons and the unused SavedReplies remain. The widget replays earlier owner messages after a page reload.
