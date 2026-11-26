# 2026-11-27 Integrations & API: "Disabled" badge clipped at narrow width

- Cause: WhatsApp Business card heading row (web/portal/src/Integrations.tsx) was a non-wrapping HStack; at 420 px the badge shrank and its label showed as "Disa...".
- Fix: that HStack gets `flexWrap: 'wrap'`, so the badge drops under the heading instead of shrinking.
- Proof: real Studio build served by demo server, Playwright viewport 420x844. Badge scrollWidth/clientWidth: before 52/43 (clipped), after 52/52 (full "Disabled").
- Mutation check done: fix removed, portal rebuilt, measured 52/43; fix restored, rebuilt, 52/52.
- Test: layout-only; repo has no portal CSS/browser test harness, so proof is the measured render above.
- Second reported issue (top nav strip overlapping "Insights / Reports" heading): NOT reproduced. Viewport (non-fullPage) screenshot at 420 px shows nav strip, pause card and heading stacked with no overlap; the earlier overlap appeared only in a fullPage screenshot (sticky topbar artifact). No change made.
