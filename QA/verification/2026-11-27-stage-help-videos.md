# 2026-11-27 Per-stage help videos for the Concierge install

Added
- 7 captioned screen walkthroughs (27-39 s each), one per Setup & Onboarding Hub stage, embedded under each stage on /guide (website/media/help/stage-N.mp4, .vtt captions, -poster.jpg). VideoObject schema for each added to the guide's JSON-LD.
- The Setup Hub in Studio now links each stage to its own video (https://trendibizz.com/guide#stage-N) plus the full walkthrough (web/portal/src/OnboardingHub.tsx).
- Built with Argo (@argo-video/cli) recording the real Studio build against the Oakridge demo data, local Kokoro voice (no cloud TTS, no payments, no synth_explainer script). Recipes live outside the repo in /Users/jo/work-staging/argo-video (tools/make_help_demos.py, tools/finish_help.py, tools/demo_server.py).
- Narration facts come from /guide and the on-screen Hub text only. No AI presenter in these (screen + voice only); the voice is synthetic and the page does not claim otherwise.

Defects found while recording, fixed
- Stage 7 scorecard badges were clipped ("Optional / Pen...") at 1920 px: row now wraps. Measured badge scrollWidth == clientWidth at 1920 and 420 px after the fix.
- website.mjs served .vtt as application/octet-stream; captions need text/vtt. Added the MIME type. Test: api/tests/test_website_case_redirect.py::test_caption_files_are_served_as_text_vtt. Mutation check done: line removed -> test fails; restored -> passes.
- Demo server (not product code) lacked /owner/mobile-connection, which made Stage 5 crash with "reading 'find'" in the recording. Mocked in argo-video/tools/demo_server.py; the real API was not involved.

Proof
- site_seo.py check OK 55 pages; full suite passed; loudness of every video -16 LUFS; each video trimmed to voice end + 1.2 s; captions timed from the pauses between sentences in the voice track.
Not done
- Captions timing is derived from silences, not forced alignment (no usable whisper model on this Mac).
- Players are small in the 3-column stage grid (fullscreen works); layout not changed.
