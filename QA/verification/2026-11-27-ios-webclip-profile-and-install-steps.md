# 2026-11-27 iPhone Web Clip profile + clearer Add to Home Screen steps

Cause: iOS has no install prompt; Share > Add to Home Screen is manual, and the steps were plain text.
Fix: `/studio/concierge.mobileconfig` (Web Clip profile, unsigned, fixed UUIDs, no ticket); install page
shows 3 big numbered steps + "You should see" line; profile offered as a collapsed fallback.
Proof: plutil -lint OK; tests in api/tests/test_pwa_install.py; mutation (FullScreen False) fails the test.
UNKNOWN: how iOS renders the unsigned profile on a real phone ("Not Verified" expected). Needs Jo to open
https://concierge.trendibizz.com/studio/concierge.mobileconfig in Safari and report.
Signing needs a paid/trusted certificate: not bought (no payments).
