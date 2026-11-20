# SESSION HANDOFF 2026-11-19g

## Git
main local, NOT pushed, NOT deployed: f4a7e21 (AI office rename, yearly plan dropped), b8dfbfd (10% annual wording + Yearly field removed), 3688fd9 (install.html: iPhone Chrome/Firefox/Edge install via own Share menu; test + QA/verification/IPHONE_CHROME_INSTALL_2026-11-19.md). Earlier work pushed to 08e705d. Use `env -u GIT_CONFIG_COUNT git`. Suite 1537 passed; `site_seo.py check` OK (46 pages).

## IN FLIGHT: Jo said "deploy it all" (explicit go for site + api + portal)
1. `env -u GIT_CONFIG_COUNT git pull --rebase`, rerun suite (scripts/dev/test-db.sh first), push.
2. `scripts/vps/deploy-site.sh`, `scripts/vps/deploy-api.sh` (138ddea api drift too).
3. Portal: web/portal/public/install.html is served from web/portal; dist/ is untracked. UNKNOWN how portal deploys (check deploy-api.sh / scripts/vps for web/portal build); make sure install.html fix reaches box.
4. `KEY=./Concierge ./scripts/vps/verify-deploy.sh` must exit 0 before saying deployed.

## Open
- Jo: Stripe deactivate yearly link 6oU28s8OH7b76528aQ04804; check monthly link tax-inclusive NZ.
- Jo: accept trendibizz owner invite (kiwi18@gmail.com), authorise email read; then `ssh -i ./Concierge root@152.42.239.240 'bash /opt/trendi/releases/20261108-vps/product/scripts/vps/check-inbound-chain.sh'`.
- iPhone Chrome install fix untested on real iPhone; Firefox/Edge wording a guess.
- SMS issue: ask Jo symptom (no real SMS, rule 6). Openmausbot: ask where seen (see SESSION_HANDOFF_2026-11-18zd.md).
- Mac concierge-stack docker calls unclassified; Jo to disable claude.ai connectors.

## Traps
Caveman replies. Never print secrets. Never stop trendi/asterisk. Never perl -pi across website without excluding _redirects.
