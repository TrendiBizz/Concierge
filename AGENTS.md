# Working agreement for agents in this repository

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
- anything the next session must know in order to resume (running services, ports, shims, seeds).

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
