# Rust telephone shell: cut-over procedure and proof (20 November 2026)

## Correction to PR #17
PR #17 added `scripts/asterisk/compose.rust.yml`, which swapped the `bridge` service for the Rust shell. That was the
wrong mechanism: production already runs the shell as its own container (`shell` in `scripts/vps/compose.yml`,
172.30.91.3) next to the Python bridge (.4), and which one answers calls is decided only by the host in the dialplan's
`AudioSocket(...)` line. That file is removed here and the README now documents the real procedure.

## What was added
- `scripts/asterisk/cutover_to_rust_shell.sh`: apply / `--rollback <dir>`, same style as `cutover_to_tenant.sh`.
  Changes only `generated/extensions.conf` (written in place, same inode) and reloads the dialplan. Does not touch
  pjsip.conf, the database, the routes, the PBX, the shell or the Python bridge. Rollback is instant and the Python
  bridge is still running.
  Refuses unless: the shell container is running; the shell has a LISTEN socket on every route port; the internal voice
  API is enabled and answers 401 to a bad token (503 means `INTERNAL_TOKEN` is unset); the carrier is Registered; no
  call is in progress. After the reload it checks every AudioSocket line points at the shell and rolls itself back if not.
- `QA/verification/asterisk_rust_shell_integration.py`: the compiled shell against the REAL FastAPI app and a REAL
  PostgreSQL database, with a fake Grok and fake callers. Same scenario and assertions as
  `asterisk_db_integration.py` (the Python bridge): two businesses, separate CRM transcripts, correct owner SMS queued
  once each, cross-business replay rejected, real sends 0.

## Proof
- Shell + real API + real DB: passes. Mutation (telephone authorization removed from the seed): the test fails.
- The cut-over script was executed end to end against the real `render_routes.py` with stand-ins for `docker` and
  `curl`: apply rewrote `bridge:9101` to `172.30.91.3:9101`, rollback restored the file byte-identical, and each refusal
  (shell down, API 503, API accepting a bad token, call in progress, port not LISTENing) left the dialplan unchanged.
- A first version accepted old log lines as proof the shell was listening; the harness exposed it and it now reads the
  socket table only (a port that appears only as a remote port of an established connection is refused).

## Not proven
- Not run on the VPS. The stand-ins cannot show the real container names or the live `phone.env`/`api.env` contents.
- No real softphone or carrier call through this exact path since the dialplan switch (a softphone call was recorded on
  11 November in HANDOFF_CURRENT_2026-11-11.md).
- `asterisk_rust_shell_integration.py` is not in the CI matrix (it needs the compiled binary).

## Addendum: found by looking at the real box (20 November 2026, evening)
- The first version of the script checked `dialplan show concierge-ingress-1` for the AudioSocket lines after the reload.
  On the real box those lines live in the per-business contexts (`[business-<slug>]`), so that check would have found
  nothing and rolled the cut-over back every time. The test stand-in had been written to answer for the wrong context,
  which hid it. Fixed: the script reads the whole dialplan, the stand-in now behaves like the real Asterisk, and
  `--dry-run` was added so the real files can be checked without changing anything.
- The live shell had been configured (compose.env, `ASTERISK_ROUTES`) for a stale staging route
  (`trendi-oauth-staging`, port 9511) while the live line is `pukeko-construction` on 9510. The script's port check
  correctly refused. compose.env was backed up and pointed at the live route and only the shell container was recreated;
  the dialplan was untouched, so the Python bridge kept answering.
- Verified on the box before any switch: shell and API internal tokens match (hash compare only), the PBX can reach
  172.30.91.3, the internal API answers 401 to a bad token.
