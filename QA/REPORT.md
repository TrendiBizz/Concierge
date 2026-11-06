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
Every module suite uses a temporary data directory (checked by grep).

## Against the REAL Twenty 2.56.0 (http://localhost:3010)
- integrations/twenty/bridge/test/live.sh: 5 of 5 pass (lead accepted, new, second post detected as duplicate, exactly one
  person in Twenty, note attached). Test person is deleted afterwards.
- Real Chrome (puppeteer-core): contact.html?plan=unlimited -> fill form -> submit -> "Thanks, we have your enquiry" -> the
  person exists in Twenty (1 match, correct name) -> no page JS errors. Cleaned up afterwards.

## Website (24 pages, ~/Downloads/concierge-build/concierge-site)
- 1760 links, 0 broken files or anchors, 0 external links, 0 links to other vendors (was 48 to GoHighLevel).
- Real headless Chrome: "Log in" links resolve to http://<same host>:3010/ (Twenty); crm.html wording corrected.

## NOT verified yet
1. Mobile menu and dropdown clicks in a browser.
2. Chat widget and calls do not feed Twenty (the site no longer claims they do).
3. All SMS, email, voice and payment providers remain stubs.
4. The old claim "import a spreadsheet" is true only in Twenty's own importer; it was not exercised here.
5. Twenty's API key expires 2027-11-06. The bridge returns 503 not_configured once it does (the form falls back to email).
6. A VM run: nothing has been booted outside this Mac.
