# SESSION HANDOFF 2026-11-18d

## Git
main, HEAD 8bac2bf, pushed. Untracked handoff files only (18a-18d). Nothing of this session committed yet.

## Done (verified by tool output)
- hermes-concierge up, Hermes v0.23.0; plugin claude-subscription-directsdk enabled v0.3.4 (profile trendi-master).
- claude CLI 2.1.326 installed in container volume /opt/data/tools (npm --prefix; ran node_modules/@anthropic-ai/claude-code/install.cjs for native binary). Symlink /usr/local/bin/claude -> it (symlink lost on container recreate; CLI stays in volume).
- `claude auth status` = loggedIn:false at 10:04.

## In flight
Jo is in a Mac terminal running `docker exec -it hermes-concierge claude login`; at the "Paste code here" prompt. Jo must open the printed URL in a Mac browser, sign in with Max account, paste returned code into the terminal. Never ask for the code in chat.

## NEXT
1. `docker exec hermes-concierge claude auth status` -> must show loggedIn true (claude.ai subscription, no API key).
2. Confirm `hermes model` lists Sonnet 5.5; set low effort; add to dashboard http://127.0.0.1:9120 Models as selectable; keep DeepSeek flash default.
3. One live test turn; confirm no API key used (0 ANTHROPIC entries in /opt/data/.env).
4. Record in QA/verification/ dated file + HANDOFF.md "Hermes master on the Mac"; note symlink trap (put in start script or PATH). Commit, `env -u GIT_CONFIG_COUNT git pull --rebase`, push.
UNKNOWN: whether plan use via this path is within Anthropic terms.

## Traps
no API billing; never print secrets/tokens; env -u GIT_CONFIG_COUNT for git; DeepSeek 402 until Jo tops up.
