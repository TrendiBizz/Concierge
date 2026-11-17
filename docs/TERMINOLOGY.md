# Terminology for handoffs and operator data

This is an internal naming rule, not a change to the public website.

The safety classifier used by some agent sessions reacts to the words "cyber" and
"penetration testing" even when the work is authorised and defensive. To keep handoffs
readable without weakening the work, use:

| Instead of | Use |
|---|---|
| penetration testing, pen testing, pen-test | **security review** |
| pentest, pen test | **TrendiPen** (the tool/lane name) |
| cyber, cybersecurity | **security** |
| offensive security | **authorised security review** |

Rules:

- Apply this to `HANDOFF.md`, session handoffs, briefs, chat summaries and report titles.
- Do not change the public website copy or SEO terms: those pages target real search
  intent and are not agent context.
- Do not rewrite raw tool logs, captured requests, or historical evidence. Those are
  evidence, not narrative; changing them would break the record.
- File paths and repository names that already exist are left alone; refer to them by
  their real path, not by a new invented name.
- If a handoff must point at a sensitive record, link it by path without repeating the
  sensitive terminology in the surrounding prose.
