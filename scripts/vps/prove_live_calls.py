"""One-off live proof for competitor-gap item B (live call supervision). Read-only + fixtures."""
import asyncio

from app import db, live_calls

SID = "synthetic:item-b-proof"


async def main():
    await db.init()
    tenant = dict(await db.pool().fetchrow(
        "SELECT * FROM tenants WHERE slug = 'pukeko-construction'"))
    tid = tenant["id"]

    for sql in (
        "DELETE FROM phone_calls WHERE call_sid = $1",
        "DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE session_id = $1)",
        "DELETE FROM conversations WHERE session_id = $1",
    ):
        await db.pool().execute(sql, SID)

    convo = await db.pool().fetchval(
        "INSERT INTO conversations(tenant_id, session_id, channel) VALUES($1,$2,'phone') RETURNING id",
        tid, SID)
    for role, content in (("assistant", "Kia ora, Pukeko Construction, how can I help?"),
                          ("user", "Yeah I'm after a price on a fence, roughly 20 metres.")):
        await db.pool().execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES($1,$2,$3)",
            convo, role, content)
    await db.pool().execute(
        """INSERT INTO phone_calls(call_sid, tenant_id, session_id, from_number, to_number,
                                   status, started_at)
           VALUES ($1,$2,$1,'+64210000001','+64900000000','in_progress', now() - interval '48 seconds')""",
        SID, tid)

    calls = await live_calls.active(tid)
    mine = [c for c in calls if c["call_sid"] == SID]
    print("active calls visible to the owner:", len(calls))
    if mine:
        call = mine[0]
        print("  caller:", call["caller"], "| seconds:", call["seconds"],
              "| caller spoken:", call["caller_has_spoken"],
              "| ring-back available:", call["ring_back_available"])
        print("  transcript tail:", [(t["who"], t["text"][:40]) for t in call["transcript"]])

    detail = await live_calls.one(tid, SID)
    print("drill-down live flag:", detail["live"] if detail else None)

    # The guardrail that matters: a finished call is no longer live, so takeover must refuse.
    await db.pool().execute(
        "UPDATE phone_calls SET status='completed', ended_at=now() WHERE call_sid=$1", SID)
    finished = await live_calls.one(tid, SID)
    print("after end -> live:", finished["live"], "| still in active():",
          any(c["call_sid"] == SID for c in await live_calls.active(tid)))

    await db.pool().execute("DELETE FROM phone_calls WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM messages WHERE conversation_id = $1", convo)
    await db.pool().execute("DELETE FROM conversations WHERE id = $1", convo)
    print("cleaned:", await db.pool().fetchval(
        "SELECT count(*) FROM phone_calls WHERE call_sid = $1", SID))
    await db.close()


asyncio.run(main())
