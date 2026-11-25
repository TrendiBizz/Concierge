# Explainer video v7 swap (2026-11-25)
- Cause: public website/media/concierge-explainer.mp4 (v6) showed internal dedupe key `enq:pukeko-demo:conv-101:1` (frame 116s) and an asterisk_bridge.py source-code panel (frame 83s).
- Fix: re-rendered from source (capture_ui_clips_v5.py dedupe key -> oakridge-demo; code panel removed, transcript-only), reassembled with assemble_v6.py. No paid calls; synth_explainer_v4.py not run.
- Proof: 206.13s, 1920x1080, 6184 frames, -14.01 LUFS; frames 83s/116s inspected clean. Speech audio reused from v6, not re-transcribed.
