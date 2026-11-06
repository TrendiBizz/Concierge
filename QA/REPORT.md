# QA report, 2026-11-06 (cloud session, run on Mac.hub)

## Automated tests (all passing)
| Suite | Tests | Result |
|---|---|---|
| crm | 13 | pass |
| calendars | 13 | pass |
| payments | 12 | pass |
| workflows | 11 | pass |
| sites | 12 | pass |
| twenty lead bridge (mock Twenty) | 18 | pass |
Every module suite uses a temporary data directory (checked by grep, not by diffing the live .db files).

## Website (24 pages, ~/Downloads/concierge-build/concierge-site)
- 1760 links, 0 broken files or anchors, 0 external links, 0 links to other vendors (was 48 to GoHighLevel).
- Real headless Chrome: "Log in" links resolve to http://<same host>:3010/ (Twenty); crm.html wording corrected;
  contact form present and reads ?plan=.
- Contact form posts to http://<host>:4410/lead and falls back to email if that fails.

## NOT verified yet
1. Twenty first-run: no workspace or API key exists. A person must create them (README in integrations/twenty/bridge).
2. A lead really landing in Twenty: run integrations/twenty/bridge/test/live.sh after step 1. Until then the bridge is
   proven only against a mock built from assumed REST shapes.
3. The contact form's success path in a browser (needs the bridge running with a key). Only the page load was checked.
4. Mobile menu and dropdown clicks were not exercised in a browser.
5. Chat widget and calls do not feed Twenty. The site no longer claims they do.
6. All SMS, email, voice and payment providers remain stubs.
