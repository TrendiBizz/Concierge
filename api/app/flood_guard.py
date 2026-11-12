"""Flood protection where messages LEAVE the platform.

Why this exists: on 2026-11-13 an owner-alert email sent to an address that routes back into the
platform came back as a "new enquiry", produced another alert, and so on: 76 emails in 20 minutes.
Every protection we had sat at an ENTRANCE (per-endpoint request limits). Nothing measured what
went OUT, six code paths inserted straight into the outbox, and the one alert throttle only applied
when a lead id was passed. So the limits below sit at the exit, where every email and text passes:

* delivery-time limits per recipient, per identical message, per business and globally
* a kill switch (``system_flags.outbound_paused``) that stops all sending immediately
* in-memory last-resort caps in the senders themselves, for anything that bypasses the outbox
* never auto-reply to robots (noreply, mailer-daemon, out-of-office)

A blocked message is never lost silently: it is stored as ``skipped`` with ``flood_guard:<reason>``
and counted by ``status()``.
"""
import hashlib
import logging
import threading
import time
from collections import defaultdict, deque
from email.utils import parseaddr

from . import db

log = logging.getLogger("concierge.flood_guard")

# Rolling-window limits applied to messages that were actually delivered.
RECIPIENT_10MIN = 8                      # one address or number, from any business
RECIPIENT_HOUR = 25
IDENTICAL_10MIN = {"email": 6, "sms": 3}  # same business + recipient + subject (email) / text (sms)
TENANT_HOUR = {"email": 100, "sms": 40}   # one business must not be able to use up everyone's budget
TENANT_DAY = {"email": 120, "sms": 150}
GLOBAL_HOUR = {"email": 150, "sms": 60}
GLOBAL_DAY = {"email": 270, "sms": 400}   # the mail provider's free plan allows 300 a day

AUTOMATED_LOCALPARTS = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
                        "postmaster", "bounce", "bounces")
AUTOMATED_SUBJECTS = ("automatic reply", "auto:", "auto-reply", "autoreply", "out of office",
                      "undeliverable", "delivery status notification", "mail delivery", "returned mail")

_COUNTS_SQL = """
SELECT
  count(*) FILTER (WHERE lower(to_addr) = $2 AND claimed_at > now() - interval '10 minutes') AS rcpt_10m,
  count(*) FILTER (WHERE lower(to_addr) = $2 AND claimed_at > now() - interval '1 hour') AS rcpt_1h,
  count(*) FILTER (WHERE tenant_id = $1 AND lower(to_addr) = $2
                     AND claimed_at > now() - interval '10 minutes'
                     AND (CASE WHEN subject <> '' THEN subject ELSE md5(body) END) = $4) AS same_10m,
  count(*) FILTER (WHERE tenant_id = $1 AND claimed_at > now() - interval '1 hour') AS tenant_1h,
  count(*) FILTER (WHERE tenant_id = $1) AS tenant_1d,
  count(*) FILTER (WHERE claimed_at > now() - interval '1 hour') AS global_1h,
  count(*) AS global_1d
FROM outbox
WHERE channel = $3 AND status IN ('sent', 'awaiting_receipt') AND claimed_at > now() - interval '1 day'
"""


def automated_message(sender: str, subject: str = "") -> bool:
    """True for robots: noreply/mailer-daemon addresses and out-of-office or bounce subjects."""
    local = (parseaddr(sender or "")[1].split("@")[0] or "").strip().lower()
    if local and any(local == p or local.startswith(p) for p in AUTOMATED_LOCALPARTS):
        return True
    return (subject or "").strip().lower().startswith(AUTOMATED_SUBJECTS)


async def check(row: dict) -> str | None:
    """Return the reason this email or text must not be sent now, or None if it may go."""
    channel = row.get("channel")
    if channel not in ("email", "sms"):
        return None
    ident = (row.get("subject") or "") or hashlib.md5((row.get("body") or "").encode()).hexdigest()
    try:
        found = await db.pool().fetchrow(
            _COUNTS_SQL, row["tenant_id"], (row.get("to_addr") or "").strip().lower(), channel, ident)
    except Exception:  # noqa: BLE001 - fail open: a broken guard must never stop a real alert
        log.exception("flood guard could not count recent sends; allowing this message")
        return None
    c = dict(found) if found else {}
    for key, limit, reason in (
        ("same_10m", IDENTICAL_10MIN[channel], "identical_10min"),
        ("rcpt_10m", RECIPIENT_10MIN, "recipient_10min"),
        ("rcpt_1h", RECIPIENT_HOUR, "recipient_hour"),
        ("tenant_1h", TENANT_HOUR[channel], "tenant_hour"),
        ("tenant_1d", TENANT_DAY[channel], "tenant_day"),
        ("global_1h", GLOBAL_HOUR[channel], "global_hour"),
        ("global_1d", GLOBAL_DAY[channel], "global_day"),
    ):
        if (c.get(key) or 0) >= limit:
            return reason
    return None


# ---- kill switch ------------------------------------------------------------------------------
_flag = {"at": 0.0, "paused": False}


async def paused() -> bool:
    """True while an operator has paused all outbound sending. Cached for 5 seconds."""
    now = time.monotonic()
    if now - _flag["at"] < 5:
        return _flag["paused"]
    try:
        value = await db.pool().fetchval("SELECT value FROM system_flags WHERE key = 'outbound_paused'")
        _flag.update(at=now, paused=(value == "1"))
    except Exception:  # noqa: BLE001 - a broken flag lookup must not stop all mail; keep the last value
        log.exception("could not read the outbound pause flag")
        _flag["at"] = now
    return _flag["paused"]


async def set_paused(value: bool, by: str = "admin") -> None:
    await db.pool().execute(
        """INSERT INTO system_flags (key, value, updated_by) VALUES ('outbound_paused', $1, $2)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by,
                                           updated_at = now()""",
        "1" if value else "0", by)
    _flag.update(at=time.monotonic(), paused=value)
    log.warning("outbound sending %s by %s", "PAUSED" if value else "resumed", by)


async def status() -> dict:
    """What an operator needs to see: paused or not, volumes against the limits, what was blocked."""
    pool = db.pool()
    sent = await pool.fetch(
        """SELECT channel,
                  count(*) FILTER (WHERE claimed_at > now() - interval '1 hour') AS last_hour,
                  count(*) AS last_day
           FROM outbox WHERE status IN ('sent', 'awaiting_receipt') AND channel IN ('email', 'sms')
             AND claimed_at > now() - interval '1 day' GROUP BY channel""")
    blocked = await pool.fetch(
        """SELECT channel, substring(last_error from 'flood_guard:(.*)') AS reason, count(*) AS n
           FROM outbox WHERE last_error LIKE 'flood_guard:%' AND created_at > now() - interval '1 day'
           GROUP BY 1, 2 ORDER BY n DESC""")
    return {
        "paused": await paused(),
        "sent": {r["channel"]: {"last_hour": r["last_hour"], "last_day": r["last_day"]} for r in sent},
        "blocked_last_day": [dict(r) for r in blocked],
        "limits": {"recipient_10min": RECIPIENT_10MIN, "recipient_hour": RECIPIENT_HOUR,
                   "identical_10min": IDENTICAL_10MIN, "tenant_hour": TENANT_HOUR,
                   "tenant_day": TENANT_DAY, "global_hour": GLOBAL_HOUR, "global_day": GLOBAL_DAY},
    }


# ---- in-memory last-resort windows ------------------------------------------------------------
_lock = threading.Lock()
_windows: dict[tuple[str, str], deque] = defaultdict(deque)


def memory_allow(kind: str, key: str, limit: int, seconds: int) -> bool:
    """Sliding-window counter for senders that bypass the outbox. Per process, resets on restart."""
    now = time.monotonic()
    with _lock:
        window = _windows[(kind, key)]
        while window and now - window[0] > seconds:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        if len(_windows) > 5000:  # keep memory bounded
            for stale in [k for k, w in _windows.items() if not w or now - w[-1] > 3600]:
                del _windows[stale]
        return True
