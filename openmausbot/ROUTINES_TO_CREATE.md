# Routines to create in openmausbot (app blocks API writes from outside the desktop app/paired device)

Zone: Pacific/Auckland. Secrets: Mac Keychain, read at run time via `security find-generic-password -s <service> -w`; never copy or print values. Draft only; no external posting without Jo's approval.

Omega Boss / Omega Harness / Dr Eggbot: definitions in ~/jo-jobs/grok-exports (omega-boss*.md, omega-harness.md, dr-eggbot*.md); not yet created.

## Master daily brief
- Bot: Chief
- Cron: `0 8 * * *`
- Prompt source: `hermes/routines/master-daily-brief.md` (drop Hermes-only names: profiles, scripts, /opt/data paths)

## Master weekly review
- Bot: Chief
- Cron: `0 10 * * 1`
- Prompt source: `hermes/routines/master-weekly-review.md` (drop Hermes-only names: profiles, scripts, /opt/data paths)

## Weekly defensive security advisories
- Bot: Trendi Desk
- Cron: `0 9 * * 3`
- Prompt source: `hermes/routines/appsec-weekly-advisories.md` (drop Hermes-only names: profiles, scripts, /opt/data paths)

