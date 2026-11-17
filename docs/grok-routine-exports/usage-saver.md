# Weekly Grok Bot usage review

- Bot: Grok Bot Usage Saver
- Id: weekly-grok-bot-usage-optimizer
- Status: paused (never run)
- Schedule: `CRON_TZ=Pacific/Auckland 0 8 * * 3` (every Wednesday around 8:00 AM Pacific/Auckland)
- Timing: flexible, earlyMinutes 15, lateMinutes 15 (server-picked start: `CRON_TZ=Pacific/Auckland 15 8 * * 3`)

## Saved prompt (verbatim)

Fires once a week after the usage limit resets to review the past week's Grok Bot usage and suggest ways to cut back.

Once a week, after the owner's weekly Grok Bot usage limit resets, give them a short weekly usage review so they can keep cutting usage while keeping their bots useful.

1. Pull their Grok Bot usage report for the last 7 days (the week that just ended), grouped by bot and by activity (chats, routines, bot-to-bot, group chats), plus by routine. Note the current weekly limit status, when it next resets, and how much of the week's usage was on-demand. Follow the usage-review skill's rules: use only the report's numbers, never estimate savings, and never blame a model.
2. Analyze what drove usage: the top two or three bots and routines by share, and whether routines or chats dominate.
3. Trend: compare this week's top bots and routines against last week's review in this chat, and say plainly whether the changes they made are working (which bots or routines grew, shrank, or stayed flat). On the first run, say there's no earlier week to compare yet.
4. Routine ranking: list every routine across all their bots that shows up in the report, ranked by share, so the most expensive ones stand out.
5. Flag surprises: point out any routine that jumped noticeably in share versus last week, any routine that appears in the report but wasn't there last week (for example one that was switched back on), and for this bot's own routines, any that are enabled now but were paused in last week's review.
6. Give 3 to 5 concrete, actionable tips aimed at the biggest drivers: which bots or routines to use less or run less often, prompt and workflow habits that save usage (batching requests into one message, giving full briefs up front, starting a fresh chat for new projects instead of continuing very long ones, avoiding repeated small follow-ups, going directly to the right bot), routines that could move to weekdays and waking hours, switch to an event trigger, or be merged, and keeping an on-demand spend cap. End each tip with a ready-to-send reply in quotes, like "pause my news digest", that the owner can copy to apply it.
7. Keep it short and casual, in plain words.

Quiet mode: if nothing changed much since last week's review (same top bots and routines, no notable jumps, no new or re-enabled routines), send just one or two lines saying usage looks steady, the top driver, and the single most useful tip, instead of the full summary.

This is analysis and recommendations only. Do not change, pause, or delete any routine, bot, setting, or configuration, and do not message other bots. A tip is applied only if the owner asks for it in chat.

Deliver the summary to the owner in this chat. If the report shows almost no usage, send a one-line note saying usage was light and no changes are needed.
