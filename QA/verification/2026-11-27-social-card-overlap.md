# 2026-11-27 Social connect card text overlap

- Cause: `.social-connect-card` (web/portal/src/shell.css) was a non-wrapping flex row; at narrow widths the title "Google Business Profile" wrapped in a tiny column and collided with the "Add another" / "Disconnect" buttons.
- Fix: card `flex-wrap: wrap`; copy `min-width/flex-basis: 120px` + `overflow-wrap: anywhere`; button group `flex: 0 0 auto; margin-left: auto`, so buttons drop to their own row instead of overlapping.
- Proof: portal build OK; fixture render of same markup at 360 px shows title on one line, buttons on the row beneath, no overlap (before: screenshot from Jo showed collision).
- Test: CSS-only layout; no CSS test harness in repo. Mutation check done: old CSS in the same fixture renders the title squeezed into a 3-line narrow column beside the buttons (fixture uses plain buttons, so no literal overlap; real Astryx buttons have min-width and overlap). New CSS: one-line title, buttons on own row.
