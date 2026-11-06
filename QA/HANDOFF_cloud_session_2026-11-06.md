# Handoff: Concierge build, cloud session (written 2026-11-06, update when state changes)

Owner: Jo (director, Trendi Limited, NZ). Rules: always full files, no snippets; never modify core code unless told clearly;
warn at ~70% context and before usage blocks; no addresses in content; original wording only; legal pages are lawyer drafts.

## Decision (Jo, option 3)
Twenty is the CRM (system of record). Our own modules do everything else. Two agents share the work:
- OpenBot "Concierge" agent (Mac app): owns ~/Concierge/{api,calendars,payments,workflows,sites,crm} and may edit the website.
- Cloud session (claude.ai/code, reaches the Mac via Desktop Commander device Mac.hub): did Twenty, the lead bridge, site fixes, QA.
Mailbox between them: ~/OpenBot/Shared/concierge-link/ (plan.md, cloud-to-openbot.md; OpenBot replies in openbot-to-cloud.md,
which did not exist at last check). Repo: TrendiBizz/Concierge, branch lmstudio-autostart, PR #2 (open). Mac git identity is the
Trendiisales user; TrendiBizz is an organization.

## What exists and is verified
- Twenty 2.56.0 in Docker: ~/Concierge/integrations/twenty (docker compose, port 127.0.0.1:3010). Workspace "Concierge" ACTIVE.
- Lead bridge: integrations/twenty/bridge (POST /lead on :4410, start with ./start.sh). 18 mock tests + test/live.sh 5/5 against real Twenty.
- Website (24 pages) at ~/Downloads/concierge-build/concierge-site (NOT in git): 48 "Log in" links now data-app-link -> http://<host>:3010/,
  crm.html claim corrected, contact form posts to http://<host>:4410/lead with mailto fallback. Backup: concierge-site.bak-20261106-144921.
  Real-browser test passes (form -> bridge -> Twenty). 1760 links, 0 broken.
- Module suites: crm 13, calendars 13, payments 12, workflows 11, sites 12, all pass. Report: QA/REPORT.md.

## Credentials (macOS login keychain, values never in files or chat)
- concierge-twenty-admin (account admin@concierge.test): Twenty admin password. concierge-twenty-api-key: API key, expires 2027-11-06.
Read one with: security find-generic-password -s <service> -w

## Open items
1. OpenBot has not replied. Ask Jo to paste: "Read ~/OpenBot/Shared/concierge-link/plan.md and cloud-to-openbot.md and reply in openbot-to-cloud.md".
2. Which to ship, the `sites` module or the 24-page website? Unanswered.
3. Chat widget (api/) and calls do not reach Twenty. Needs OpenBot's api to call the bridge, or n8n.
4. Stubs: SMS, email, voice, payments. Label them on screen.
5. Mobile menu and dropdown not click-tested. VM run not done (Docker daemon exists on the Mac; Jo wanted a VM test).
6. Site files are not in git. Decide whether to add them to the repo.
7. Twenty Docker volume is test data only. If wiped, rerun the setup scripts in integrations/twenty/.bootstrap-scratch (untracked):
   sign up via /metadata signUp, signUpInNewWorkspace(input:{displayName}), getAuthTokensFromLoginToken, activateWorkspace,
   createApiKey + generateApiKeyToken. NEVER rerun the workspace step if a workspace exists (it creates another).

## Gotchas
- Desktop Commander: commands containing `sleep` or long loops often return no output via read_process_output; poll with short commands.
- Edit/Read tools act on the cloud container, not the Mac; use Desktop Commander start_process for Mac files.
- Mock-only tests proved nothing about Twenty: my first guessed note field (`personId`) was wrong, the real one is `targetPersonId`.
- Twenty auth/API for sign-up lives on /metadata, not /graphql. Introspection needs auth; its own frontend chunks (served at /assets) show call shapes.
- GitHub GraphQL is blocked in the cloud session; use gh api REST. Cloud clone /home/user/concierge is old main, not the work branch.

## Next steps, in order
1. Get OpenBot's reply; settle item 2.
2. Wire chat widget and bookings to POST /lead.
3. VM test: docker compose for Twenty + bridge + site; run live.sh there.
4. Click-test mobile nav; update QA/REPORT.md; push.

## HARD RULE from Jo: NO GoHighLevel actions
Never enable or change anything on GoHighLevel (sub-accounts, reselling, Custom Menu Links, snapshots, billing). Concierge replaces it.
If a task seems to need it, stop and ask Jo. Earlier OpenBot handoffs list a "GHL Custom Menu Link" step: do not do it.
