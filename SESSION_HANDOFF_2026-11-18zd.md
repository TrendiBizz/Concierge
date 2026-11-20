# SESSION HANDOFF 2026-11-18zd

## Git
main 51b6205 pushed (dd2783c Ego Lite deleted + openmausbot/ROUTINES_TO_CREATE.md; 51b6205 count fix). 82c7a51 cold-solicitation filter deployed, verify-deploy exit 0. Suite 1528 pass.

## Direction
Jo leaves Hermes (unhappy) and Grok (arbitrary usage rules) for openmausbot (installed ~/.openmausbot, v0.1.169, server 127.0.0.1:8799, bots: SEO Engine, Workwatch, Omega Harness, Trendi Desk, Omega Boss, Chief; 12 routines already present). Jo: "full access", export everything, secrets STAY in Mac Keychain and bots point there (security find-generic-password -s <svc> -w, never copy/print). Ego Lite deleted (repo only; live Hermes job on box untouched, was paused). Hermes not retired until Jo says.

## NEXT ACTION (Jo's last ask: "figure out how we do this")
Writes to routines/bots are 403 from outside the app: "must come from the desktop app or a paired device" (deliberate guard; do NOT bypass or hand-edit routines.json/bots.json). Ways: (a) Jo pastes from openmausbot/ROUTINES_TO_CREATE.md in the desktop app; (b) `openmausbot pair` (single-use code) so this session is a paired device. Ask Jo which. Check bot MCP server / headless-cli docs (openmausbot-docs skill only has SKILL.md locally) for a supported create route.
To create: Master daily brief (Chief 0 8 * * *), Master weekly review (Chief 0 10 * * 1), Weekly defensive security advisories (Trendi Desk 0 9 * * 3), zone Pacific/Auckland, prompts from hermes/routines/*.md minus Hermes-only names, plus Keychain note. Then Omega Boss / Omega Harness / Dr Eggbot routines+skills from ~/jo-jobs/grok-exports (omega-boss*.md, omega-harness.md, dr-eggbot*.md) not yet created. Put Keychain pointer in bot standing instructions (bots.json via app).

## Open
- TechDay email: drafted 2026-11-18, NEVER SENT. Jo to confirm send.
- FB/IG daily + LinkedIn weekly posting: openmausbot routines say draft only; ships a social-posts skill (check it). Need Jo: auto-post vs veto queue (recommend veto). No FB/IG/LinkedIn token found in Keychain yet.
- Keychain move: Jo hasn't confirmed done. Names only listed (jo-otp seeds etc.); no trendi-* keys seen in truncated list.
- Gmail filter zenithen2.com: manual by Jo.
- Earlier: weekly-engine-health job rerun; ~/jo-brain c94fdd5 unpushed; omega-desk MCP restore from ~/.claude/removed-mcp-2026-11-18.json.

## Traps
macOS sed needs -i ''. git: env -u GIT_CONFIG_COUNT. Caveman replies, plain honest, no unflagged inference. Never print secrets.
