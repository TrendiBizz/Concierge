# SESSION HANDOFF 2026-11-19i

## Git / deploy
main at b4c13b7 (checkpoint over 3688fd9). Site/api/portal deployed, verify-deploy OK earlier. Use `env -u GIT_CONFIG_COUNT git`.
UNCOMMITTED: web/portal/src/App.tsx ~785 wording "iPhone: in Safari, Chrome, Firefox or Edge, Share -> Add to Home Screen" (not built/deployed). Harmless; build (pnpm run build in web/portal), commit, suite, push, deploy-studio.sh, verify-deploy.sh.

## IN FLIGHT: Studio install QR fails on Jo's iPhone Chrome
FACT: curl with iPhone Chrome UA -> /studio/install and /studio/install/ 200 text/html; trendibizz.com 200; concierge root 307 fast. DNS A+AAAA Cloudflare. Box journal (box is UTC) shows no iPhone request: only my curls. Jo screenshots: ERR_FAILED, then blank page + "took too long to respond" at 08:31 NZDT (Wi-Fi+cell bars shown).
Jo was asked: (1) open https://trendibizz.com in iPhone Chrome, (2) Wi-Fi off, open concierge URL on cellular. Jo replied only "doesnt load" - UNKNOWN which URL/test. Ask which; if trendibizz.com also fails = phone/network, not repo.
INFERENCE (unverified): phone network path (IPv6/Wi-Fi/DNS) to Cloudflare, not our server. No repo defect found; nothing to fix yet.
Next: get Jo's answer to tests 1 and 2; if only concierge host fails, check Cloudflare rules (WAF/bot/country/rate) for that hostname.

## Open for Jo
Stripe yearly link deactivate (6oU28s8OH7b76528aQ04804); trendibizz owner invite + email-read auth then check-inbound-chain.sh; SMS symptom (no real SMS); Firefox/Edge wording guess.

## Traps
Caveman replies. Never print secrets. Never stop trendi/asterisk. No perl -pi across website (excl _redirects).
