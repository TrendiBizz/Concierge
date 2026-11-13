# The screens — Team, Your CRM, and addresses on a contact — 2026-11-13

Closes the gap left by `f5a6c4c`: the API and guarantees existed, but a customer could not use any
of it.

## What was built

**Team** (`/owner/team`) — the member list with role, state and "you", an invite form that returns
the single-use link, and pending invitations.

```
GET   /owner/team                    everyone may look
PATCH /owner/team/{id}               owner only — viewer/editor/owner
POST  /owner/team/{id}/deactivate    owner only — access ends, sessions deleted
POST  /owner/team/{id}/reactivate    owner only
```

Guards, each with its own message: you cannot remove your own access, a business must keep at
least one owner (cannot demote or deactivate the last), a person from another business is 404, and
only an owner may change anything.

**Your CRM** — export as CSV or JSON, paste-a-CSV import, and the webhook (save / send queued /
remove).

**Also reachable at** — on any contact, every phone number and email that belongs to that person,
with add and remove.

## Two bugs found by testing, both fixed

**23. The export buttons did 401.** `window.location.href = '/owner/export/contacts?format=csv'` is
a plain navigation, and auth here is a bearer token held in memory, not a cookie — so the browser
sent no credentials and the API refused. The button looked like a download and did nothing.
Fixed by fetching with the header and handing the bytes to the browser as a blob. Caught by a
browser test waiting on a `download` event: red before, `customers.csv` after.

**24. My own test harness hung for ten minutes.** A FastAPI `TestClient` runs the app in its own
thread and event loop, so the asyncpg pool created by `asyncio.run()` was bound to a loop that had
already closed, and the first request waited forever. The team suite now drives the same app object
with `httpx.ASGITransport` inside one loop: 6 tests in 2.8s. This is a tooling defect, and it is
recorded here because the rule covers our own tooling.

## Proof, live, in production

`api/tests/test_team.py` — 6 tests against a real Postgres, mutation-checked (removing the
self-removal guard fails the suite). Full suite **1007 passed**, 9 skipped without a database.

Browser, on `concierge.trendibizz.com/studio`, signed in through a real single-use invite:

```
Team loads             members listed                    ok
own row protected      you marked                        ok
role change            now editor (persisted)            ok
remove access          badge shown                       ok
restore access         restored                          ok
Your CRM loads         download buttons present          ok
CSV download           customers.csv                     ok
contact card opens     Timeline + address section        ok
addresses listed       phone and email                   ok
add an address         appears in the list               ok
remove an address      gone from the list                ok
JS / 5xx errors        0                                 ok
```

Test data created for this run (one contact, one spare user, one address) was deleted afterwards.

## Still open

The **team list is per member, not per invitation reminder** — an invitation is only re-sendable by
creating a new one. Not built: audit trail of who viewed what, and SSO. Neither was asked for.
