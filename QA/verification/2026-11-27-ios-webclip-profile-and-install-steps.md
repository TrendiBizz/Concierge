# 2026-11-27 iPhone Web Clip profile + clearer Add to Home Screen steps

Cause: iOS has no install prompt; Share > Add to Home Screen is manual, and the steps were plain text.
Fix: `/studio/concierge.mobileconfig` (Web Clip profile, unsigned, fixed UUIDs, no ticket); install page
shows 3 big numbered steps + "You should see" line; profile offered as a collapsed fallback.
Proof: plutil -lint OK; tests in api/tests/test_pwa_install.py; mutation (FullScreen False) fails the test.
UNKNOWN: how iOS renders the unsigned profile on a real phone ("Not Signed" expected). Needs Jo to open
https://concierge.trendibizz.com/studio/concierge.mobileconfig in Safari and report.
Signing needs a paid/trusted certificate: not bought (no payments).

## Addendum: profile is now the lead iPhone route (Jo: "it does work", wants every step shown)
Install page iPhone card: 5 big numbered steps (Download > Allow > Settings Profile Downloaded > Install/passcode > tap icon), each with a "you should see" line; Share-menu route kept in a collapsed section. Copy-link / not-in-Safari help stay visible. Test: test_iphone_card_leads_with_five_step_profile_install_and_keeps_share_route; mutation (rename "Profile Downloaded") fails it.

## Addendum 2: easier sign-in (Jo: "email me a code or sign-in link needs to be easier")
Cause: an installed iPhone app has empty storage, so a plain install lands on the email-code screen. The signed-in QR already carried a ticket via the manifest, but the profile did not.
Fix: profile route takes ?k=ticket (format-checked, same 1h ticket) so the Web Clip opens at /studio/#invite=ticket; install page passes #k= to the profile link. Code screen: iOS code autofill (one-time-code, numeric), auto-submit at 6 digits, email remembered on device, Enter sends.
Proof: test_webclip_profile_opens_signed_in_only_with_a_well_formed_ticket; suite 1983 passed. UNKNOWN: whether a managed Web Clip shares storage with Safari (ticket path assumed like the manifest path); needs Jo's phone.

## Addendum 3: where the signed-in QR is
Cause: PhoneInstall (the ticketed install QR) lived only in LegacySetup, which nothing renders: the QR was unreachable in the live Studio. Fix: render it on the Home tab (hidden once installed); copy now describes the iPhone profile steps. Check: open Studio Home on a computer, QR visible below the dashboard.

## Addendum 4: drawn step pictures (Jo: still confusing, show screens)
Each of the 5 profile steps now has an inline SVG drawing of the iPhone screen with the tap target outlined, captioned as a drawing (not a real screenshot). Checked in WebKit iPhone 13 emulation. Real iPhone screenshots from Jo can replace them.

## Addendum 5 — real screenshots (2026-11-27)
- Cause: drawn pictures guessed iOS wording; Jo's real iPhone showed "Not Signed" and a 10-step flow (Warning screen, passcode, confirm dialog).
- Fix: /studio/install now uses Jo's real screenshots in web/portal/public/install-steps/ (cropped, light-blue outline on each tap target; Settings crop drops name/Wi-Fi). Steps 2 (Allow pop-up) and 10 (Home Screen) stay drawings, not captured. "Not Verified" -> "Not Signed".
- Proof: suite 1983 passed; mutation (Not Signed -> Not Verified in page) makes test_pwa_install fail.
