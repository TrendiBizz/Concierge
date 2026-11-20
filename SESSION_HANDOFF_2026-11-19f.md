# SESSION HANDOFF 2026-11-19f

## Git
main has local commit f4a7e21 (site: AI receptionist -> AI office, URLs+301s, yearly removed, OG=title, 3-mo min on pricing card). NOT pushed, NOT deployed. Earlier work pushed (138ddea..08e705d). Use `env -u GIT_CONFIG_COUNT git`. Suite 1536 passed; `site_seo.py check` OK.

## IN FLIGHT (do first)
Jo: "we removed yearly price, so remove ALL verbiage around the 10% discount for annual payment". Grep website/ (html, llms.txt, site-i18n.json, products.js, chatgpt-products.csv, JSON-LD) for "10%", "save", "annual", "per year", "yearly", "225" ; rerun `python3 scripts/seo/site_seo.py sitemap --write` and `check`, run suite, amend/commit. Note perl on `.html` earlier also re-serialised JSON-LD in ~23 pages (whitespace only).

## Done this session
- Owner invite sent for tenant trendibizz to kiwi18@gmail.com (queued). Jo must accept, sign in, Permissions -> authorise email read. Then re-run on box: `ssh -i ./Concierge root@152.42.239.240 'bash /opt/trendi/releases/20261108-vps/product/scripts/vps/check-inbound-chain.sh'` (trendibizz was only live FAIL: owner_account, consent).
- AI receptionist -> AI office done (virtual-receptionist left as is; ask Jo if to change).

## Open
1. Deploy: `scripts/vps/deploy-site.sh` + `deploy-api.sh` (138ddea drift) need Jo's go; then `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. Push after suite + `git pull --rebase`.
2. Stripe (Jo): deactivate yearly link 6oU28s8OH7b76528aQ04804; check monthly link tax setting is tax-inclusive for NZ; no extra GST wording.
3. SMS issue unresolved, not started (no real SMS/calls; rule 6). Start in repo SMS gateway records (scripts/vps/SMS_FREE_GATEWAY.md, PHONE_SETUP.md); ask Jo for symptom.
4. Openmausbot (Jo's bot service): connection/permission problem, nothing found in repo; check SESSION_HANDOFF_2026-11-18zd.md; ask Jo where seen.
5. Mac concierge-stack/ docker calls unclassified; token baseline; Jo to disable claude.ai connectors.

## Traps
Caveman replies. Never print secrets. Never stop trendi/asterisk. Test DB: scripts/dev/test-db.sh first. Never perl -pi across website without excluding _redirects.
