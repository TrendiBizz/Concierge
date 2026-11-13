# Working agreement for agents in this repository

## The bug rule — permanent, immutable, always enacted

**Every bug or defect encountered in a session is fixed, tested and documented in that same
session.** This rule outranks feature work, tidying, and the session-length limit: when they
collide, hand off at a clean boundary *after* the bug is landed, never before it. It cannot be
waived, relaxed, or traded away, and it is not satisfied by a workaround that hides the defect.

It applies to **every** defect, however small, and to our own tooling — scripts, tests, deploy
commands, configuration — not only to product code. It applies whether or not the human noticed
it. Silence is the failure mode this rule exists to prevent.

Each bug requires all three, in the same session:

1. **Fixed** — the defect itself.
2. **Tested** — a check that fails without the fix and passes with it. Mutate the fix once and
   watch that check go red before trusting it. Where the defect is operational (a deploy
   command, a wrong hostname, a broken script), the test is the corrected command run and its
   recorded output.
3. **Documented** — cause, fix and proof, in that date's `QA/verification/` record, and in the
   repo's working agreement when it changes how others should work.

"There is no time", "come back to it", "known issue", "it is probably fine" and "try again later"
are **not permitted outcomes**.

The single exception is a bug that cannot be fixed in-session because something outside our
control blocks it. That is not permission to defer quietly: record the exact blocker, what was
tried, why it could not proceed, and an explicit open item with a next action in the handoff's
Outstanding list. Evidence, then deferral — never a shrug.

## Session length limit

**Work in units of at most ~25 tool calls, or one coherent unit of work — whichever comes first.**

When the limit is reached: stop, report state, and hand off. Do not drift into "one more check".

Why this exists: the DSH Web GUI degrades as a session accumulates tool calls — after roughly
250 calls in a session, tool invocations start rendering in the chat as raw XML (`<bash>`,
`<parameter>`) instead of appearing as executed steps. The commands still run and their results
still arrive, but the human can no longer read the conversation. Recovering means restarting the
web server and repinning the browser tab, which is disruptive. Starting a fresh session well
before that point is much cheaper.

A unit of work here is typically: one route or one port batch, plus its vectors, tests, mutation
checks, gate run and status update. If a unit cannot be finished inside the budget, stop at a
coherent boundary and write down exactly where the work stands, rather than leaving a
half-applied change.

### Handoff format

Leave, at the end of the response when stopping:

- what is committed (with the commit hash) and what is not;
- the exact files modified but uncommitted;
- anything the next session must know in order to resume (running services, ports, shims, seeds);
- **the outstanding list, carried forward in full** — blockers, known bugs, security items and
  unverified features. Update `QA/verification/HANDOFF_CURRENT_<date>.md` with it, and make the
  workspace `HANDOFF.md` name that file as "read first" plus summarise its Outstanding section.
  A handoff that reports only the task just finished is incomplete, even when that task is done.

## Repository-specific notes

- `scripts/rust-gate.sh` must pass before any push. Never pipe it — an earlier
  `cargo clippy | grep | head` hid lint failures and shipped red CI twice. Run `cargo fmt` on
  the affected crates *after* the last edit, since the gate's `--check` fails otherwise.
- Parity vectors come from the live Python (`parity/gen_vectorsNN.py` -> `vectorsNN.json`),
  never typed by hand. Reading the Python and retyping field lists has failed repeatedly.
- Mutate each new rule once and see a test fail before trusting it. A passing test that has
  never been seen to fail proves nothing.
- A differential harness run is the only thing that proves a route. Unit tests cannot catch a
  wrong SQL parameter type or a wrong path-matching rule.
- Local verification needs PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`). CI supplies its
  port through `CONCIERGE_TEST_POSTGRES_PORT`; the harness defaults to 55432 locally, and a
  `psql` shim may be needed on hosts without a PostgreSQL client.
