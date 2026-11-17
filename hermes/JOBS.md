# Migration map: Grok Bot schedules and procedures -> Hermes

This is the audit trail for the move. It records every Trendi/Concierge Grok
automation, where its procedure came from, and what Hermes does with it. The
machine-readable version is `schedules.yaml`; this file explains the gaps.

The Grok **Omega** bots are not in this migration. They belong to a different
project and keep their own owner.

## Active

| Grok automation (id) | Procedure source | Hermes job | Profile | Schedule (NZDT) |
|---|---|---|---|---|
| Daily site + search monitor (Trendi) (`daily-site-search-monitor-trendi`) | `~/OpenBot/Shared/workwatch/routines/seo-daily-monitor.md` | `seo-daily-monitor` | seo-engine | 07:40 daily |
| Weekly SEO cycle (Trendi) (`weekly-seo-cycle-trendi`) | `routines/seo-weekly-cycle.md` | `seo-weekly-cycle` | seo-engine | Mon 09:00 |
| Monthly SEO audit (Trendi) (`monthly-seo-audit-trendi`) | `routines/seo-monthly-audit.md` | `seo-monthly-audit` | seo-engine | 1st 09:00 |
| Innovation scout (Trendi) (`innovation-scout-trendi`) | `routines/seo-innovation-scout.md` | `seo-innovation-scout` | seo-engine | 8th & 22nd 10:00 |
| Trendi LinkedIn weekly draft (`trendi-linkedin-weekly-draft`) | `routines/trendi-linkedin-weekly.md` | `trendi-linkedin-weekly` | trendi-desk | Mon 09:30 |
| Trendi biweekly SEO + pen-test news (`trendi-biweekly-seo-pen-test-news`) | `routines/trendi-biweekly-news.md` | `trendi-biweekly-news` | trendi-desk | 1st & 15th 10:30 |
| Trendi daily SEO / pen-test social drafts | `~/OpenBot/Shared/workwatch/ops/social/PROMPT.md` | `trendi-social-drafts` | trendi-desk | 07:00 daily |
| Trendi SEO forums daily deep dive | `HANDOVER.md` section 15b | `trendi-deep-dive` | trendi-desk | 07:30 daily |
| Twice-monthly post brief (Trendi) (`twice-monthly-post-brief-trendi`) | Recorded creation + content rules (see the procedure; the verbatim Grok prompt was not in the local cache) | `trendi-post-brief` | trendi-desk | 3rd & 17th 09:00 |
| Workwatch weekly report | Workwatch README (8 days collected, 7 reported) | `workwatch-weekly-report` | workwatch | Mon 08:00 |
| — (new) | Master layer over the subagents | `master-daily-brief` | trendi-master | 08:00 daily |
| — (new) | Master layer over the subagents | `master-weekly-review` | trendi-master | Mon 10:00 |

## Paused, with the exact prerequisite

| Grok automation (id) | Hermes job | Why paused | How to enable |
|---|---|---|---|
| trendibizz.com daily tamper watch (`trendibizz-com-daily-tamper-watch`) | `trendi-tamper-watch` | No read-only Cloudflare token on the Mac; the tamper kit is not in `trendi-site` | T1 below |
| Ego Lite Linux watch (`ego-lite-linux-watch`) | `ego-lite-linux-watch` | One-shot; no Linux build exists | Re-enable when a Linux build ships, or delete the job |

## Prerequisites

**T1 — tamper watch.** Jo creates a read-only Cloudflare API token (DNS, Zone, Zone
Settings, Firewall, Workers Routes Read; Pages, Workers Scripts, Account Settings,
Notifications Read). The kit (`cf-snapshot.js`, `daily_watch.py`,
`daily-watch.sh`, baselines) is committed to `trendi-site/scripts/security/`. Then:

```bash
docker exec hermes-concierge hermes -p site-watch cron resume <id>
```

and run it once by hand. Review every flag against the change ledger before accepting
any baseline. Never accept the mail DNS or DMARC items.

**T2 — Workwatch notes. DONE 2026-11-17.** Jo asked for Workwatch to be part of the
Hermes setup and UI. `~/.workwatch/notes` is mounted read-only at
`/opt/data/.workwatch/notes`, and `workwatch-weekly-report` is active (Mon 08:00). The
routine still refuses to print raw shell history, credentials or personal detail.

## Pause the remaining Trendi automations in Grok Bot

The six Workwatch launchd labels are disabled on the Mac. The Grok Bot cloud copies
cannot be paused from this repo. Jo must **pause (not delete)** these in Grok Bot, or
they can double-run with Hermes:

1. Daily site + search monitor (Trendi)
2. Weekly SEO cycle (Trendi)
3. Monthly SEO audit (Trendi)
4. Innovation scout (Trendi)
5. Trendi LinkedIn weekly draft
6. Trendi biweekly SEO + pen-test news
7. Trendi daily SEO / pen-test social drafts
8. Trendi SEO forums daily deep dive
9. Twice-monthly post brief (Trendi)
10. trendibizz.com daily tamper watch
11. Ego Lite Linux watch

The Hermes copies of 10 and 11 are paused until their prerequisites are met, so pausing
the Grok copies is safe. Once each Hermes copy has a successful scheduled run, the Grok
copy can be deleted.

## What changed in the move

- The **schedule owner** is Hermes cron, not launchd or the Grok box. `--catch-up on`
  means a missed 07:30 run happens once when the Mac wakes, instead of being skipped.
- The **model** is still Grok (the xAI key in the profile). The prompt and the limits
  are the Workwatch text; only the paths and the Python interpreter are adapted.
- The **delivery** is a report file (`~/.workwatch/reports/hermes/...`) instead of a
  chat message. The master reads the files. Jo reads `latest.md` or the master brief.
- The **customer-facing** Hermes (`hermes-trendi-support` on the VPS) is unchanged and
  still restricted to todo, memory and session_search. It is not the master.

## Not moved on purpose

- The Omega trade/ research bots and their routines.
- The OpenBot agents (Boss, Workwatch, Trendi, SEO/Pen test Manager); their ownership
  was revoked on 2026-11-15 and their work is back with the Grok owners.
- The Grok box's `/workspace/trendi` data. The Mac copies are the current source; the
  box data stopped on 2026-11-06.
- Deploying the Concierge API or the VPS. That stays a human action with the repo's
  `scripts/vps` gate.
