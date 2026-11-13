"""Web Push for owner alerts: a notification on the owner's own phone or computer, through the portal.

An owner opens the portal (/owner-ui), taps "Turn on alerts on this device", and the browser gives the
server a private push address. Each owner alert then also becomes a short notification on that device.
No SIM, no carrier and no extra app. Email alerts continue unchanged and remain the backup.

Safeguards
  * Only the real push services are accepted as a destination (Google, Mozilla, Apple, Microsoft), over
    https on the default port. The server never connects to an address an owner typed in.
  * Payloads are encrypted end to end by the Web Push standard; the text is kept short and carries no links.
  * At most HOURLY_CAP pushes per business per hour, and the same alert is pushed once per DEDUPE_SECONDS.
  * A subscription the push service reports gone (404/410) is deleted; repeated failures stop it being used.
  * Nothing here can fail an alert: every error is logged and swallowed.
"""
import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import time
from urllib.parse import urlsplit

from . import db
from .config import get_settings

log = logging.getLogger("concierge.webpush")

PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "push.services.mozilla.com",
              "push.apple.com", "notify.windows.com")
MAX_PER_TENANT = 10
MAX_FAILURES = 5
HOURLY_CAP = 30
DEDUPE_SECONDS = 600

_hits: dict[str, list[float]] = {}
_seen: dict[str, float] = {}
_URL = re.compile(r"https?://\S+")


def configured() -> bool:
    settings = get_settings()
    return bool(settings.vapid_private_key and settings.vapid_public_key)


def allowed_endpoint(endpoint: str) -> bool:
    """True only for an https address on one of the real push services (default port, no credentials)."""
    try:
        parts = urlsplit(endpoint or "")
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or not host or parts.username or parts.password or port not in (None, 443):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return any(host == known or host.endswith("." + known) for known in PUSH_HOSTS)


def make_payload(subject: str, body: str, dedupe: str = "") -> str:
    """The notification text: a short title and one short line, with no links."""
    title = " ".join((subject or "").split())[:80] or "New alert"
    text = " ".join(_URL.sub("", body or "").split())
    if len(text) > 140:
        text = text[:137].rstrip() + "..."
    tag = hashlib.sha1((dedupe or title).encode()).hexdigest()[:16]
    return json.dumps({"title": title, "body": text, "url": "/owner-ui", "tag": tag}, separators=(",", ":"))


def _allow(tenant_id: str, dedupe: str, now: float | None = None) -> bool:
    """Per-business hourly cap and short-term de-duplication. In memory: a restart only resets the counters."""
    now = time.monotonic() if now is None else now
    stamps = [t for t in _hits.get(tenant_id, []) if now - t < 3600]
    if len(stamps) >= HOURLY_CAP:
        _hits[tenant_id] = stamps
        return False
    key = tenant_id + ":" + hashlib.sha1((dedupe or "").encode()).hexdigest()
    if dedupe and now - _seen.get(key, -1e9) < DEDUPE_SECONDS:
        return False
    stamps.append(now)
    _hits[tenant_id] = stamps
    if dedupe:
        _seen[key] = now
    if len(_seen) > 2000:
        for old in [k for k, t in _seen.items() if now - t >= DEDUPE_SECONDS]:
            _seen.pop(old, None)
    return True


def _send_blocking(endpoint: str, p256dh: str, auth: str, data: str) -> str:
    """One push. Returns "ok", "gone" (the device unsubscribed) or "error". Runs in a worker thread."""
    try:
        from pywebpush import WebPushException, webpush
    except Exception:  # noqa: BLE001 - the library is missing: treat as a failure, never crash an alert
        log.exception("pywebpush is not installed")
        return "error"
    settings = get_settings()
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=3600,
            timeout=10,
        )
        return "ok"
    except WebPushException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code not in (404, 410):
            log.warning("push failed (%s)", code)
        return "gone" if code in (404, 410) else "error"
    except Exception:  # noqa: BLE001
        log.warning("push failed (%s)", "exception")
        return "error"


async def _deliver(row, data: str) -> str:
    outcome = await asyncio.to_thread(_send_blocking, row["endpoint"], row["p256dh"], row["auth"], data)
    pool = db.pool()
    if outcome == "ok":
        await pool.execute("UPDATE push_subscriptions SET last_ok_at=now(), failures=0 WHERE id=$1", row["id"])
    elif outcome == "gone":
        await pool.execute("DELETE FROM push_subscriptions WHERE id=$1", row["id"])
    else:
        await pool.execute("UPDATE push_subscriptions SET failures=failures+1 WHERE id=$1", row["id"])
    return outcome


async def notify(tenant: dict, subject: str, body: str, dedupe: str = "") -> int:
    """Push one owner alert to every subscribed device of the business. Returns how many were sent. Never raises."""
    try:
        if not configured() or not _allow(str(tenant["id"]), dedupe):
            return 0
        rows = await db.pool().fetch(
            "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE tenant_id=$1 AND failures < $2",
            tenant["id"], MAX_FAILURES)
        if not rows:
            return 0
        data = make_payload(subject, body, dedupe)
        sent = 0
        for row in rows:
            if await _deliver(row, data) == "ok":
                sent += 1
        return sent
    except Exception:  # noqa: BLE001 - an alert must never fail because a push did
        log.exception("web push notify failed")
        return 0


async def save(tenant_id, endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> None:
    pool = db.pool()
    await pool.execute(
        "INSERT INTO push_subscriptions(tenant_id,endpoint,p256dh,auth,user_agent) VALUES($1,$2,$3,$4,$5) "
        "ON CONFLICT (endpoint) DO UPDATE SET tenant_id=EXCLUDED.tenant_id, p256dh=EXCLUDED.p256dh, "
        "auth=EXCLUDED.auth, user_agent=EXCLUDED.user_agent, failures=0",
        tenant_id, endpoint, p256dh, auth, (user_agent or "")[:300])
    await pool.execute(
        "DELETE FROM push_subscriptions WHERE tenant_id=$1 AND id NOT IN "
        "(SELECT id FROM push_subscriptions WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2)",
        tenant_id, MAX_PER_TENANT)


async def remove(tenant_id, endpoint: str) -> None:
    await db.pool().execute(
        "DELETE FROM push_subscriptions WHERE tenant_id=$1 AND endpoint=$2", tenant_id, endpoint)


async def send_test(tenant_id, endpoint: str) -> dict:
    """Send a test notification to one device the signed-in owner has just turned on."""
    if not configured():
        return {"sent": 0, "note": "Phone alerts are not set up on this server yet."}
    row = await db.pool().fetchrow(
        "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE tenant_id=$1 AND endpoint=$2",
        tenant_id, endpoint)
    if not row:
        return {"sent": 0, "note": "This device is not turned on for alerts."}
    data = make_payload("Test alert", "Your Concierge alerts are working on this device.", "test:" + str(time.time()))
    outcome = await _deliver(row, data)
    return {"sent": 1 if outcome == "ok" else 0, "result": outcome}
