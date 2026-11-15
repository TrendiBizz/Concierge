# Harness git environment fault — 2026-11-16

**Scope:** our tooling (the agent harness), not product code. Recorded here because it silently
disabled every git command in the agent shell, including the deploy gate.

## Symptom

Every git command in the agent shell failed, in every repository:

```
error: missing config key GIT_CONFIG_KEY_0
fatal: unable to parse command-line config
```

`git --version` worked; `git status`, `git log`, `git ls-files` all died. Consequences:
`scripts/vps/deploy-site.sh` could not check for a dirty tree, `scripts/vps/verify-deploy.sh`
could not hash git state, and the suite's `tests/test_no_live_secrets_committed.py` failed
because it shells out to `git ls-files`.

## Cause

The harness spawns every child through a credential scrub in
`@deepseek-ai/dsh-subprocess/lib/index.js`:

```js
const SENSITIVE_ENV_PATTERN = /KEY|PASSWORD|SECRET|TOKEN/i;
```

Any ambient name matching `/KEY/` is dropped. Git's command-line config overrides are
`GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_n`, `GIT_CONFIG_VALUE_n` — so `GIT_CONFIG_KEY_0` matched and
was removed, while `GIT_CONFIG_COUNT=1` and `GIT_CONFIG_VALUE_0=false` passed through. The `dsh
web` process carried all three (`ps eww` on PID 71681: `GIT_CONFIG_COUNT=1
GIT_CONFIG_KEY_0=core.quotePath GIT_CONFIG_VALUE_0=false`), so every child got a *partial* git
config block. Git treats that as a syntax error and refuses to run at all.

The scrub was half-right for the wrong reason: removing the key alone is the one shape guaranteed
to break git. Passing the whole family through would be worse — ambient `GIT_CONFIG_*` can inject
config such as `core.sshCommand` into every child.

## Fix

Exclude the entire family from the inherited environment, as a family:

```js
const GIT_CONFIG_ENV_PATTERN = /^GIT_CONFIG_/i;
// ... in scrubbedParentEnv():
!SENSITIVE_ENV_PATTERN.test(key) && !GIT_CONFIG_ENV_PATTERN.test(key) && !DSH_*
```

Spawners that genuinely need overrides (workspace snapshots, the forge panel) already pass the
whole family explicitly, and explicit env merges after the scrub, so they are unaffected.

Patched file: `/Users/jo/.npm-global/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-subprocess/lib/index.js`.

## Test and mutation proof

`~/.dsh/tooling-tests/subprocess-env-scrub.test.mjs` (node:test, 2 tests) sets the exact polluted
parent env, calls `scrubbedParentEnv()`, and asserts (a) no `GIT_CONFIG_*` name survives, (b) a
child with that env runs `git status`, and (c) an explicit full-family override still merges.

- Green: `node --test ~/.dsh/tooling-tests/subprocess-env-scrub.test.mjs` → **2 pass**.
- Mutation: removed the `&& !GIT_CONFIG_ENV_PATTERN.test(key)` clause → **both tests failed**, the
  second with the exact production error `error: missing config key GIT_CONFIG_KEY_0`. Restored →
  green again.

Operational proof in the repo suite: `tests/test_no_live_secrets_committed.py` failed 1/3 while
the stale env was live and passed 3/3 under `env -u GIT_CONFIG_COUNT` (see
`TEST_ENV_2026-11-16.md`).

## Residual, and why this is not "closed" yet

A running harness process keeps the old module in memory, so the shell stayed broken until the
`dsh web` process restarts. In the meantime `env -u GIT_CONFIG_COUNT <command>` is the bridge, and
it is now documented in the repo's `AGENTS.md` under "Agent shell environment".

The patch lives in an installed npm package: a `dsh` upgrade will overwrite it. It belongs upstream
in `@deepseek-ai/dsh-subprocess`; carried as an open item in `HANDOFF.md` §3 until it is.
