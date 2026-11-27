# 2026-11-27 iPhone Web Clip profile + clearer Add to Home Screen steps

Cause: iOS has no install prompt; Share > Add to Home Screen is manual, and the steps were plain text.
Fix: `/studio/concierge.mobileconfig` (Web Clip profile, unsigned, fixed UUIDs, no ticket); install page
shows 3 big numbered steps + "You should see" line; profile offered as a collapsed fallback.
Proof: plutil -lint OK; tests in api/tests/test_pwa_install.py; mutation (FullScreen False) fails the test.
UNKNOWN: how iOS renders the unsigned profile on a real phone ("Not Verified" expected). Needs Jo to open
https://concierge.trendibizz.com/studio/concierge.mobileconfig in Safari and report.
Signing needs a paid/trusted certificate: not bought (no payments).

## Addendum: profile is now the lead iPhone route (Jo: "it does work", wants every step shown)
Install page iPhone card: 5 big numbered steps (Download > Allow > Settings Profile Downloaded > Install/passcode > tap icon), each with a "you should see" line; Share-menu route kept in a collapsed section. Copy-link / not-in-Safari help stay visible. Test: test_iphone_card_leads_with_five_step_profile_install_and_keeps_share_route; mutation (rename "Profile Downloaded") fails it.
