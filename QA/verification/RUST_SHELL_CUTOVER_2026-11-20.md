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
