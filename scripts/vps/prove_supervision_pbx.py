"""Live-PBX proof of the supervision path: originate → ChanSpy leg → audit row → Stop → closed.

Run inside the api container so the real settings, code and database are used:

    docker cp prove_supervision_pbx.py trendi-api-1:/tmp/
    docker exec -u root trendi-api-1 chmod 644 /tmp/prove_supervision_pbx.py
    docker exec -w /srv -e PYTHONPATH=/srv trendi-api-1 python /tmp/prove_supervision_pbx.py

No carrier traffic and no PSTN number is dialled. The caller and the supervisor's phone are
stand-ins: two Local channels into a temporary ``[supervision-test]`` dialplan context that
answers and waits. That exercises everything except the audio itself and the real handset:

* the synthetic caller is found by ``CONCIERGE_CALL``, exactly as a Hero call is;
* ``attach_supervisor`` rings the stand-in and runs the real ``ChanSpy``;
* ``CONCIERGE_SPY`` is read back off the live channel;
* the audit row is opened before the ring and closed by ``stop_supervision``;
* ``Stop`` ends the leg — and, after the 2026-11-12 fix, never the caller's channel.

The dialplan context is temporary; add it to the deployed generated/extensions.conf and run
``asterisk -rx "dialplan reload"`` first::

    [supervision-test]
    exten => 100,1,Answer()
     same => n,Wait(300)
     same => n,Hangup()
    exten => 200,1,Answer()
     same => n,Wait(300)
     same => n,Hangup()
"""
import asyncio
import secrets
import sys
import uuid

from app import asterisk_ami, call_control, db, live_calls, supervision
from app.config import get_settings

CALLER_DIAL = "Local/100@supervision-test"
SUPERVISOR_DIAL = "Local/200@supervision-test"
SUPERVISOR_NUMBER = "200"


def note(label, value):
    print(f"[prove] {label}: {value}", flush=True)


async def main() -> int:
    config = asterisk_ami.from_settings(get_settings())
    if not config:
        note("AMI", "NOT CONFIGURED")
        return 2
    note("AMI", repr(config))
    await db.init()

    tenant_id = await db.pool().fetchval(
        "INSERT INTO tenants (slug, name, public_key) VALUES ($1, $2, $3) RETURNING id",
        "spy-probe-" + secrets.token_hex(3), "Supervision probe", secrets.token_hex(8))
    call_sid = "ast:" + str(uuid.uuid4())
    caller = None
    passed = False
    try:
        await asterisk_ami.originate(
            config, CALLER_DIAL, "Wait", "300",
            variables={"CONCIERGE_CALL": call_sid[4:]}, timeout_ms=15000)
        await asyncio.sleep(1.5)
        caller = await call_control.channel_for(call_sid, config)
        note("synthetic caller channel", caller)
        if not caller:
            note("RESULT", "FAIL: the caller was not found by CONCIERGE_CALL")
            return 3

        marker = secrets.token_hex(8)
        record = await supervision.start(
            tenant_id, call_sid, "listen",
            supervisor="probe", number="+6421000000", marker=marker)
        note("audit row", record)

        spy = await call_control.attach_supervisor(
            call_sid, SUPERVISOR_NUMBER, "listen",
            channel_dial=SUPERVISOR_DIAL, spy_marker=marker, config=config)
        note("attach_supervisor returned", spy)
        note("is that the caller's channel?", spy == caller)
        if not spy or spy == caller:
            note("RESULT", "FAIL: attach_supervisor did not name the supervisor's leg")
            return 4
        await supervision.attach_channel(record["id"], spy)

        legs = await call_control.spy_legs(config)
        note("spy legs", legs)
        readback = await asterisk_ami.get_variable(config, spy, "CONCIERGE_SPY")
        note("CONCIERGE_SPY read back", readback)
        if (readback or "").strip() != marker:
            note("RESULT", "FAIL: CONCIERGE_SPY read back wrong")
            return 5

        result = await live_calls.stop_supervision({"id": tenant_id}, call_sid, by="probe")
        note("Stop result", result)
        await asyncio.sleep(1.5)

        legs_after = await call_control.spy_legs(config)
        note("spy legs after Stop", legs_after)
        row = dict(await db.pool().fetchrow(
            "SELECT * FROM supervision_sessions WHERE id = $1", record["id"]))
        note("audit row after Stop", {key: row[key] for key in
                                      ("ended_at", "ended_reason", "spy_channel")})
        if result["stopped"] != 1 or row["ended_at"] is None:
            note("RESULT", "FAIL: Stop did not close exactly one leg")
            return 6
        if any(value == marker for value in legs_after.values()):
            note("RESULT", "FAIL: a channel carrying the marker survived Stop")
            return 7
        if caller not in [channel for channel in legs_after]:
            # The caller's own channel must still be there: Stop ends the supervisor, not the call.
            live_names = [c.get("Channel") for c in await asterisk_ami.channels(config)]
            if caller not in live_names:
                note("RESULT", "FAIL: Stop hung up the caller's channel")
                return 8
        passed = True
        note("RESULT", "PASS: leg named by marker, read back, Stop closed the row and the leg")
        return 0
    finally:
        for channel in (caller,):
            if channel:
                try:
                    await asterisk_ami.hangup(config, channel)
                except asterisk_ami.AmiError:
                    pass
        for channel, marker in (await call_control.spy_legs(config)).items():
            try:
                await asterisk_ami.hangup(config, channel)
            except asterisk_ami.AmiError:
                pass
        await db.pool().execute("DELETE FROM tenants WHERE id = $1", tenant_id)
        left = await db.pool().fetchval(
            "SELECT count(*) FROM supervision_sessions WHERE tenant_id = $1", tenant_id)
        note("fixtures left", left)
        note("probe outcome", "PASS" if passed else "FAIL")
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
