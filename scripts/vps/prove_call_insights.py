"""One-off live proof for competitor-gap item D (after-call intelligence).

Creates a synthetic finished call with a short transcript, runs the real analysis path (which calls
the configured model once), prints the result, then removes every fixture it created.
"""
import asyncio

from app import call_insights, db

SID = "synthetic:item-d-proof"
TENANT_SLUG = "pukeko-construction"


async def main():
    await db.init()
    tenant = dict(await db.pool().fetchrow(
        "SELECT * FROM tenants WHERE slug = $1", TENANT_SLUG))
    tid = tenant["id"]

    await db.pool().execute("DELETE FROM call_insights WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM phone_calls WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM messages WHERE conversation_id IN "
                            "(SELECT id FROM conversations WHERE session_id = $1)", SID)
    await db.pool().execute("DELETE FROM conversations WHERE session_id = $1", SID)

    convo_id = await db.pool().fetchval(
        """INSERT INTO conversations(tenant_id, session_id, channel)
           VALUES($1, $2, 'phone') RETURNING id""", tid, SID)
    for role, content in (
        ("assistant", "Kia ora, you have reached Pukeko Construction. How can I help?"),
        ("user", "Hi, I need a quote for a new driveway. It's about 40 square metres."),
        ("assistant", "Thanks. I can book a site visit with the team. Would Thursday morning work?"),
        ("user", "Thursday is good but I want someone to call me first to talk about pricing."),
        ("assistant", "No problem, I have asked the team to call you today."),
    ):
        await db.pool().execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES($1,$2,$3)",
            convo_id, role, content)
    await db.pool().execute(
        """INSERT INTO phone_calls(call_sid, tenant_id, session_id, from_number, to_number,
                                   status, started_at, ended_at)
           VALUES ($1,$2,$1,'+64210000001','+64900000000','completed',
                   now() - interval '3 minutes', now())""", SID, tid)

    call = dict(await db.pool().fetchrow("SELECT * FROM phone_calls WHERE call_sid = $1", SID))
    result = await call_insights.analyse_call(tenant, call)
    print("analysis:", result)

    row = await db.pool().fetchrow(
        "SELECT outcome, sentiment, model, left(summary, 90) AS summary "
        "FROM call_insights WHERE call_sid = $1", SID)
    print("persisted:", dict(row) if row else None)
    tasks = await db.pool().fetch(
        "SELECT title FROM tasks WHERE tenant_id = $1 AND kind = 'call_back' "
        "AND created_at > now() - interval '5 minutes'", tid)
    print("follow-up tasks created:", [t["title"] for t in tasks])
    print("recent() returns it:",
          any(r["call_sid"] == SID for r in await call_insights.recent(tid, 20)))

    # remove fixtures, including any task this proof created
    await db.pool().execute("DELETE FROM tasks WHERE tenant_id = $1 AND kind = 'call_back' "
                            "AND lead_id IS NULL AND created_at > now() - interval '5 minutes'", tid)
    await db.pool().execute("DELETE FROM call_insights WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM messages WHERE conversation_id = $1", convo_id)
    await db.pool().execute("DELETE FROM conversations WHERE id = $1", convo_id)
    await db.pool().execute("DELETE FROM phone_calls WHERE call_sid = $1", SID)
    print("cleaned; insights left for that call:",
          await db.pool().fetchval("SELECT count(*) FROM call_insights WHERE call_sid = $1", SID))
    await db.close()


asyncio.run(main())
