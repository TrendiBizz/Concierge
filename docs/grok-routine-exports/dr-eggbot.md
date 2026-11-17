# dr eggbot routines (both PAUSED, never run)

## transcript-healthcheck
- name: transcript-healthcheck
- id: transcript-healthcheck
- status: paused
- schedule: CRON_TZ=Pacific/Auckland 44 8 * * 1-5 (weekdays ~08:44 NZ)
- timing: flexible, earlyMinutes 15, lateMinutes 15 (server-picked start 08:48)
- saved prompt (verbatim):

```
Run the Transcript healthcheck skill. Window: since the last successful run, or the last 24h if unknown. Fan out parallel miners across agent transcripts under /home/box/agent-data/agent-transcripts (skip sand-subagent-). Report friction and proposals (skill | bot | routine) to the user. Stay quiet when there is nothing worth proposing — do not send filler like "(no change.)". Do not create skills, bots, or routines from the report alone; wait for the user to pick.
```

## routine-healthcheck
- name: routine-healthcheck
- id: routine-healthcheck
- status: paused
- schedule: CRON_TZ=Pacific/Auckland 49 8 * * 1 (Mondays ~08:49 NZ)
- timing: flexible, earlyMinutes 15, lateMinutes 15 (server-picked start 08:34)
- saved prompt (verbatim):

```
Run the Routine healthcheck skill. Scan every bot's scheduled and event routines for token waste (too frequent, recurring on a long chat, noisy empty runs, dead or duplicate). Report a short list: bot, routine, flag, suggested fix. Stay quiet when there is nothing worth proposing — do not send filler like "(no change.)". Do not edit another bot's routines unless the user says to.
```

Skills referenced: "Transcript healthcheck" and "Routine healthcheck" (in /home/box/agent-data/workflows). No secrets.
