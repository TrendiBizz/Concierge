# Routine: Ego Lite Linux watch

- Profile: `trendi-desk`
- Schedule: `0 9 * * 1` Pacific/Auckland
- Source: Grok Trendi Desk automation `ego-lite-linux-watch`; verbatim prompt in
  jo-brain `profiles-full/trendi-desk-to-openbot-workwatch.md` D
- Status: **paused** — one-shot; no Linux build has shipped
- Approval: watch only; installing anything needs Jo's yes

## Procedure

Check whether the ego lite browser (GitHub `citrolabs/ego-lite`, site
`lite.ego.app`) now has a real Linux build:

- the latest GitHub releases;
- the README platform line;
- the open Linux feature request (issue #140);
- the `lite.ego.app` download/roadmap pages.

Only a downloadable Linux app (deb, AppImage, rpm, tarball or a working Linux install
path) counts. A roadmap mention or comment does not.

- **If a Linux build exists:** tell Jo (version, link, install method), then propose
  the plan to make it usable for the Trendi bots on the shared Linux box (install it
  there, sign it into Trendi social media accounts only, never banking/Stripe/
  payments, add the ego-browser skill). Wait for Jo's yes before installing anything.
  Then this routine can be deleted.
- **If there is no Linux build:** write `Status: quiet` and send nothing.

## Output

Write `~/.workwatch/reports/hermes/trendi-desk/<date>-ego-lite-linux-watch.md` and
update `latest.md`. A quiet week is one line.
