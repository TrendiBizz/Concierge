"""The supervision audit trail — who listened to which call, and for how long.

The phone receptionist now tells callers that a team member may listen to the call, so
listening has to be provable rather than merely intended. Every listen / whisper / join is a
row: the tenant, the call, the mode, the person who asked, the number their phone was rung on,
when the leg opened and when it closed.

Two rules keep the record honest:

* A duration is only ever ``ended_at - started_at``. An open leg reports "so far" at read time
  and is never stored as a completed session.
* A leg closes for exactly one reason, and the reason is recorded: the supervisor stopped it,
  their phone hung up, or the call itself ended. A failed ring is recorded too — an attempted
  listen that never connected has a duration of zero and says so.
"""

import logging
from datetime import datetime, timezone

from . import db

log = logging.getLogger("concierge.supervision")

#: What a supervisor mode is called in front of a person.
MODES = {"listen": "Listen in", "whisper": "Whisper", "join": "Join"}

STOPPED = "the supervisor stopped it"
HUNG_UP = "the supervisor's phone hung up"
CALL_ENDED = "the call ended"
CALL_REMOVED = "the call was removed"
RING_FAILED = "the supervisor could not be rung"


def label(mode) -> str:
    """A mode's human label; an unknown mode is still reported, never hidden."""
    return MODES.get(str(mode or "").strip().lower(), str(mode or "").strip().title())


def duration_seconds(row: dict, now: datetime | None = None) -> int:
    """Seconds the leg was open: to ``ended_at`` if closed, to ``now`` if still open. Never < 0."""
    now = now or datetime.now(timezone.utc)
    started = row.get("started_at")
    if not started:
        return 0
    ended = row.get("ended_at") or now
    return max(0, int((ended - started).total_seconds()))


def summarise(row: dict, now: datetime | None = None) -> dict:
    """One supervision leg as the audit view shows it. Pure, so the API and console agree."""
    ended = row.get("ended_at")
    return {
        "id": row.get("id"),
        "call_sid": row.get("call_sid") or "",
        "caller": row.get("from_number") or "",
        "mode": str(row.get("mode") or ""),
        "mode_label": label(row.get("mode")),
        "supervisor": row.get("supervisor") or "",
        "number": row.get("supervisor_number") or "",
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "ended_at": ended.isoformat() if ended else None,
        "seconds": duration_seconds(row, now),
        "open": ended is None,
        "ended_reason": row.get("ended_reason") or "",
    }


async def start(tenant_id, call_sid: str, mode: str, *, supervisor: str = "",
                number: str = "", marker: str = "") -> dict:
    """Open a leg's record *before* it is dialled, so an attempted listen is never invisible."""
    row = await db.pool().fetchrow(
        """INSERT INTO supervision_sessions
               (tenant_id, call_sid, mode, supervisor, supervisor_number, marker)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING id, started_at""",
        tenant_id, str(call_sid)[:200], str(mode).strip().lower(), str(supervisor)[:200],
        str(number)[:40], str(marker)[:40],
    )
    return dict(row)


async def attach_channel(supervision_id, channel: str) -> None:
    """Remember which PBX channel carries the leg, so it can be ended and reconciled."""
    await db.pool().execute(
        "UPDATE supervision_sessions SET spy_channel = $2 WHERE id = $1",
        supervision_id, str(channel or "")[:200],
    )


async def stop(tenant_id, supervision_id, reason: str = STOPPED) -> dict | None:
    """Close one leg. Returns the closed row, or ``None`` if it was already closed."""
    row = await db.pool().fetchrow(
        """UPDATE supervision_sessions
              SET ended_at = now(), ended_reason = $3
            WHERE tenant_id = $1 AND id = $2 AND ended_at IS NULL
        RETURNING *""",
        tenant_id, supervision_id, str(reason)[:200],
    )
    return dict(row) if row else None


async def open_for_call(tenant_id, call_sid: str) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT * FROM supervision_sessions
            WHERE tenant_id = $1 AND call_sid = $2 AND ended_at IS NULL
            ORDER BY started_at""",
        tenant_id, str(call_sid)[:200],
    )
    return [dict(row) for row in rows]


async def active_by_call(tenant_id) -> dict[str, list[dict]]:
    """Every open leg for a tenant, grouped by the call it is attached to."""
    rows = await db.pool().fetch(
        """SELECT * FROM supervision_sessions
            WHERE tenant_id = $1 AND ended_at IS NULL ORDER BY started_at""",
        tenant_id,
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row["call_sid"]), []).append(dict(row))
    return grouped


async def close_ended_calls(tenant_id) -> int:
    """Close legs whose call is over. The call's own end time is the honest end of listening."""
    rows = await db.pool().fetch(
        """UPDATE supervision_sessions s
              SET ended_at = COALESCE(pc.ended_at, now()), ended_reason = $2
             FROM phone_calls pc
            WHERE s.tenant_id = $1 AND s.ended_at IS NULL
              AND pc.tenant_id = s.tenant_id AND pc.call_sid = s.call_sid
              AND pc.status <> 'in_progress'
        RETURNING s.id""",
        tenant_id, CALL_ENDED,
    )
    removed = await db.pool().fetch(
        """UPDATE supervision_sessions s
              SET ended_at = now(), ended_reason = $2
            WHERE s.tenant_id = $1 AND s.ended_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM phone_calls pc
                               WHERE pc.tenant_id = $1 AND pc.call_sid = s.call_sid)
        RETURNING s.id""",
        tenant_id, CALL_REMOVED,
    )
    closed = len(rows) + len(removed)
    if closed:
        log.info("closed %s supervision leg(s) because their call ended or was removed", closed)
    return closed


async def close_missing_legs(tenant_id, live_channels, reason: str = HUNG_UP) -> int:
    """Close legs whose PBX channel has gone — the supervisor hung up their own phone.

    ``live_channels`` is the set of channels the PBX still reports; a leg with a known channel
    that is no longer in it has ended, whatever the console still thinks.
    """
    live = {str(channel) for channel in (live_channels or set()) if channel}
    rows = await db.pool().fetch(
        """SELECT id, spy_channel FROM supervision_sessions
            WHERE tenant_id = $1 AND ended_at IS NULL AND spy_channel <> ''""",
        tenant_id,
    )
    closed = 0
    for row in rows:
        if row["spy_channel"] in live:
            continue
        if await stop(tenant_id, row["id"], reason):
            closed += 1
    if closed:
        log.info("closed %s supervision leg(s) the PBX no longer has", closed)
    return closed


async def recent(tenant_id, limit: int = 20) -> list[dict]:
    """The audit view: newest first, with the caller's number where the call still exists."""
    rows = await db.pool().fetch(
        """SELECT s.*, pc.from_number
             FROM supervision_sessions s
             LEFT JOIN phone_calls pc
                    ON pc.tenant_id = s.tenant_id AND pc.call_sid = s.call_sid
            WHERE s.tenant_id = $1
            ORDER BY s.started_at DESC LIMIT $2""",
        tenant_id, max(1, min(int(limit), 100)),
    )
    return [summarise(dict(row)) for row in rows]
