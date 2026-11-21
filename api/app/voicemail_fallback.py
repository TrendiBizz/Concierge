"""Voicemail taken by the PBX when the AI voice link is down (N3).

The dialplan (scripts/asterisk/render_routes.py --voicemail-dir) records the caller into a spool
directory as `<tenant-slug>__<call-uuid>__<caller-digits>.wav`. This worker turns each file into the
same things a normal call produces: a phone_calls row, a CRM enquiry for the caller's number, the
stored recording, and the owner alert (which goes out through the owner's paired phone like every
other alert). Off unless VOICEMAIL_SPOOL_DIR is set. Idempotent: the call_sid is unique and a file is
only removed once it is stored; a file that cannot be stored yet stays for the next sweep.
"""

import asyncio
import logging
import re
import secrets
import time
from pathlib import Path

from fastapi import HTTPException

from . import convo, db, enquiries, enquiry_alerts, tenants, voice_records
from .config import get_settings

log = logging.getLogger("concierge.voicemail")

NAME = re.compile(r"^(?P<slug>[a-z0-9][a-z0-9-]{0,79})__(?P<call>[0-9a-f-]{8,64})__(?P<num>\d{0,15})\.wav$")
SETTLE_SECONDS = 15        # Asterisk may still be writing a file this young
MIN_BYTES = 8000 + 44      # about one second of 8 kHz PCM: shorter is silence or a hang-up click
MAX_BYTES = 8 * 1024 * 1024


def parse_name(name: str) -> dict | None:
    m = NAME.match(name)
    return m.groupdict() if m else None


async def _process(path: Path, tenant: dict, parts: dict) -> str:
    call_id = "vm:" + parts["call"]
    caller = ("+" + parts["num"]) if parts["num"] and len(parts["num"]) >= 8 else parts["num"]
    body = path.read_bytes()
    async with db.pool().acquire() as c:
        inserted = await c.fetchval(
            "INSERT INTO phone_calls(tenant_id,call_sid,from_number,to_number,status) VALUES($1,$2,$3,$4,'voicemail') "
            "ON CONFLICT DO NOTHING RETURNING 1", tenant["id"], call_id, caller, "")
    if not inserted:
        return "duplicate"
    conversation = await convo.get_or_create(tenant, call_id, "phone", None, None)
    capability = await voice_records.start(tenant, call_id, channel="phone")
    session = await voice_records.authenticate(capability["id"], capability["token"])
    # The caller was told by the pre-recorded greeting that a message would be recorded.
    session["recording_consent"] = True
    await db.pool().execute("UPDATE voice_sessions SET recording_consent=true WHERE id=$1", session["id"])
    lead = await enquiries.capture(tenant, "phone", call_id, "Voicemail left while the AI receptionist was unavailable",
                                   conversation_id=conversation, phone=caller)
    tail = "Voicemail received: our AI receptionist could not take this call, so the caller left a message."
    try:
        await voice_records.store_audio(session, body, "audio/wav")
        token = secrets.token_urlsafe(32)
        await db.pool().execute(
            "INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id) VALUES($1,$2,$3)",
            voice_records.digest(token), session["id"], tenant["id"])
        tail += "\n\nRecording (private link expires in 24 hours): " + \
            get_settings().public_base_url.rstrip("/") + "/api/v1/voice/recordings/shared/" + token
        stored = True
    except HTTPException as error:
        stored = False
        tail += f"\n\nThe recording could not be stored ({error.detail}). The file is kept on the server for you to collect."
    owner = await db.pool().fetchval("SELECT owner_number FROM managed_phone_setups WHERE tenant_id=$1", tenant["id"])
    owner = owner or tenant.get("notify_phone")
    lead_id = lead.get("id") if isinstance(lead, dict) else None
    await enquiry_alerts.notify(tenant, "phone", tail + "\n\nCaller: " + (caller or "number withheld"),
                                lead_id=lead_id, conversation_id=conversation, finalize=True, owner_phone=owner)
    await db.pool().execute("UPDATE phone_calls SET ended_at=now() WHERE tenant_id=$1 AND call_sid=$2", tenant["id"], call_id)
    return "stored" if stored else "kept"


async def sweep(directory: str | None = None) -> dict:
    root = Path(directory or get_settings().voicemail_spool_dir)
    result = {"stored": 0, "kept": 0, "duplicate": 0, "skipped": 0, "errors": 0}
    if not str(root) or not root.is_dir():
        return result
    kept = root / "kept"
    for path in sorted(root.glob("*.wav")):
        parts = parse_name(path.name)
        stat = path.stat()
        if not parts or time.time() - stat.st_mtime < SETTLE_SECONDS or stat.st_size > MAX_BYTES:
            result["skipped"] += 1
            continue
        if stat.st_size < MIN_BYTES:
            path.unlink()        # no message: a hang-up click is not a voicemail
            result["skipped"] += 1
            continue
        try:
            tenant = await tenants.get_by_slug(parts["slug"])
            if not tenant:
                result["skipped"] += 1
                continue
            outcome = await _process(path, tenant, parts)
            if outcome == "kept":
                kept.mkdir(exist_ok=True)
                path.rename(kept / path.name)
            else:
                path.unlink()
            result[outcome] += 1
        except Exception:
            result["errors"] += 1
            log.exception("Voicemail %s will be retried", path.name)
    return result


async def run_forever(stop: asyncio.Event, interval: float = 30.0) -> None:
    if not get_settings().voicemail_spool_dir:
        return
    while not stop.is_set():
        try:
            await sweep()
        except Exception:
            log.warning("Voicemail sweep will retry", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
