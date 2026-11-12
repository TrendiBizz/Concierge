"""One-off live proof for competitor-gap item A (missed-call text-back). Removes its own fixtures."""
import asyncio

from app import db, missed_calls

SID = "synthetic:item-a-proof"


async def main():
    await db.init()  # a fresh interpreter has no pool
    t = await db.pool().fetchrow("SELECT * FROM tenants WHERE slug = 'pukeko-construction'")
    tenant = dict(t)
    print("tenant:", tenant["slug"], "| textback:", tenant["missed_call_textback"],
          "| sms_enabled:", tenant["sms_enabled"])

    await db.pool().execute("DELETE FROM missed_call_recoveries WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM phone_calls WHERE call_sid = $1", SID)
    # A call that fails back to the business's own number: exercises the whole decision + audit
    # write path, and by construction can never text a stranger.
    await db.pool().execute(
        """INSERT INTO phone_calls(call_sid, tenant_id, session_id, from_number, to_number,
                                   status, started_at, ended_at)
           VALUES ($1, $2, NULL, '+64900000000', '+64900000000', 'completed',
                   now() - interval '12 seconds', now())""",
        SID, tenant["id"],
    )
    call = dict(await db.pool().fetchrow("SELECT * FROM phone_calls WHERE call_sid = $1", SID))

    loaded = await missed_calls.evaluate_call_sid(SID)
    print("evaluate_call_sid:", loaded)

    row = await db.pool().fetchrow(
        "SELECT status, reason, contact FROM missed_call_recoveries WHERE call_sid = $1", SID)
    print("audit row:", dict(row) if row else None)

    # Real tenant, real rules: an unanswered call from a number that never booked.
    print("rules on the live tenant (silent call, real caller):", missed_calls.decide(
        tenant=tenant, call={**call, "from_number": "+64210000001", "to_number": "+64900000000"},
        caller_turns=0, has_appointment=False, recovered_recently=False,
        sms_authorized=tenant["sms_enabled"]))
    print("rules when the tenant switches it off:", missed_calls.decide(
        tenant={**tenant, "missed_call_textback": False},
        call={**call, "from_number": "+64210000001", "to_number": "+64900000000"},
        caller_turns=0, has_appointment=False, recovered_recently=False, sms_authorized=True))

    await db.pool().execute("DELETE FROM missed_call_recoveries WHERE call_sid = $1", SID)
    await db.pool().execute("DELETE FROM phone_calls WHERE call_sid = $1", SID)
    left = await db.pool().fetchval(
        "SELECT count(*) FROM missed_call_recoveries WHERE call_sid = $1", SID)
    print("cleaned, fixtures left:", left)
    await db.close()


asyncio.run(main())
