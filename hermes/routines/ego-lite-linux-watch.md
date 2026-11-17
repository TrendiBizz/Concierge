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

Write `/opt/data/.workwatch/reports/hermes/trendi-desk/<date>-ego-lite-linux-watch.md` and
update `latest.md`. A quiet week is one line.


## Required report completion

Use the current **Pacific/Auckland** calendar date (`YYYY-MM-DD`), including on
catch-up runs; note the scheduled date separately if different. UTC topic selection
in a routine does not change the report date.

1. Create `/opt/data/.workwatch/reports/hermes/trendi-desk/` if missing.
2. Use `write_file` or a terminal file write to save the actual findings to
   `/opt/data/.workwatch/reports/hermes/trendi-desk/<YYYY-MM-DD>-ego-lite-linux-watch.md`.
   This is the canonical routine report; supplementary drafts do not replace it.
3. Begin with `# ego-lite-linux-watch — <YYYY-MM-DD>` and a plain, unbolded
   `Status: quiet | attention | needs Jo | blocked` line (choose one).
4. Copy the same content to `/opt/data/.workwatch/reports/hermes/trendi-desk/latest.md`.
5. Use a file tool to **read back** both files and confirm their content matches.
   Complete these writes even for quiet, blocked or no-news runs, before returning
   a final response or `[SILENT]`. Returning text does not save a report.
6. If writing or verification fails, return `[CRON_FAILURE]` on the first line,
   followed by `WRITE FAILED`, the path and the error. Claim success only after
   the read-back succeeds. Never fabricate findings to satisfy this contract.
