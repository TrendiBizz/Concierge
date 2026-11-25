# Explainer video v8: remove dedupe key line (2026-11-25)

- **Cause:** v7 only renamed `pukeko-demo` to `oakridge-demo` in the owner-alert card; the internal line "Dedupe key: enq:oakridge-demo:conv-101:1" stayed visible ~113s to ~122s. The v7 commit title and QA note overstated the change.
- **Fix:** removed the "Dedupe key" field from the owner-alert demo HTML in `capture_ui_clips_v5.py` (job dir `~/jo-jobs/concierge-video-v7`), re-captured only `04a_owner_alert_demo.mp4`, reassembled (`assemble_v8.py`, speech audio reused, no synthesis, no paid calls). Replaced `website/media/concierge-explainer.mp4`.
- **Proof:** ffprobe 206.13s, 1920x1080, -14.01 LUFS; frames at 83s and 116s checked by eye: header shows From/To/Channels only, no dedupe key. Deploy and verify-deploy results recorded in the session handoff.
