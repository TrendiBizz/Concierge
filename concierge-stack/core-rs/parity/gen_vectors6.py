"""Batch-6 golden vectors: owner SMS shortening, recording validation, calendar sync (the real sync_one against a scripted provider).

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors6.py > ../concierge-stack/core-rs/parity/vectors6.json
"""
import asyncio
import json
import os
import random
import re
import struct
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
from fastapi import HTTPException

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import calendar_connection as cc, db, owner_notifications, voice_records  # noqa: E402

rng = random.Random(20261114)
UTC = timezone.utc

# ---- owner SMS body ---------------------------------------------------------------------------------------
sms_cases = []
LINK = "https://chat.example.test/recordings/shared/abc123XYZ"
for blen in (0, 100, 1399, 1400, 1401, 1500, 3000):
    for links in ([], [LINK], [LINK, LINK + "2"], ["http://x.test/y/recordings/shared/q?z=1"]):
        for base in ("https://chat.example.test", "https://chat.example.test/", "http://localhost:8000//"):
            for subj in ("New lead", "S" * 200, "Café ünï"):
                body = ("é" if blen % 2 else "b") * blen
                if links and blen >= 1400:
                    body = body[: blen // 2] + " " + " ".join(links) + " " + body[blen // 2:]
                owner_notifications.get_settings = lambda b=base: SimpleNamespace(public_base_url=b)
                sms_cases.append({"subject": subj, "body": body, "base": base, "out": owner_notifications.sms_body(subj, body)})
sms_cases = rng.sample(sms_cases, 160)

# ---- voice recordings --------------------------------------------------------------------------------------
digest_cases = [{"in": t, "out": voice_records.digest(t)} for t in ["", "tok", "é日本😀", "x" * 300]]


def wav(channels=1, width=2, rate=8000, frames=100, fmt_tag=1, extra_chunk=False, data_before_fmt=False, trunc=0, size_override=None, riff="RIFF", wave="WAVE"):
    data = b"\x01\x00" * (frames * channels * width // 2) if width == 2 else b"\x01" * (frames * channels * width)
    fmtc = b"fmt " + struct.pack("<IHHIIHH", 16, fmt_tag, channels, rate, rate * channels * width, channels * width, width * 8)
    datac = b"data" + struct.pack("<I", len(data) if size_override is None else size_override) + data
    if trunc:
        datac = datac[:-trunc]
    parts = [datac, fmtc] if data_before_fmt else [fmtc, (b"LIST" + struct.pack("<I", 4) + b"abcd") if extra_chunk else b"", datac]
    body = wave.encode() + b"".join(parts)
    return riff.encode() + struct.pack("<I", len(body)) + body


bodies = {
    "webm": b"\x1aE\xdf\xa3" + b"\x00" * 20, "webm_short": b"\x1aE\xdf\xa3" + b"\x00" * 5, "webm_bad": b"XXXX" + b"\x00" * 20,
    "ogg": b"OggS" + b"\x00" * 20, "mp4": b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 12, "mp4_bad": b"\x00\x00\x00\x18ftXpmp42" + b"\x00" * 12,
    "wav_ok": wav(), "wav_rate": wav(rate=16000), "wav_stereo": wav(channels=2), "wav_8bit": wav(width=1), "wav_24bit": wav(width=3), "wav_nonpcm": wav(fmt_tag=3),
    "wav_extra": wav(extra_chunk=True), "wav_data_first": wav(data_before_fmt=True), "wav_trunc": wav(trunc=40), "wav_odd": wav(frames=101), "wav_zero": wav(frames=0),
    "wav_big_claim": wav(size_override=10_000_000), "wav_bad_wave": wav(wave="WAVX"), "wav_junk": b"RIFF" + b"\x00" * 30,
    "wav_extensible": wav(fmt_tag=0xFFFE),
}
CT = {"webm": "audio/webm", "ogg": "audio/ogg", "mp4": "audio/mp4"}
audio_cases = []
for name, body in bodies.items():
    cts = [CT.get(name.split("_")[0], "audio/wav")]
    cts += ["AUDIO/WAV; codecs=1", " audio/webm ;x=y", "audio/mpeg", "", "audio/wav"] if name in ("wav_ok", "webm") else ([("audio/wav" if name.startswith("wav") else CT.get(name, "audio/webm"))] if False else [])
    for ct in cts:
        try:
            out = {"ok": voice_records.audio_type(ct, body)}
        except HTTPException as e:
            out = {"err": [e.status_code, e.detail]}
        audio_cases.append({"name": name, "ct": ct, "body_hex": body.hex(), "out": out})

# ---- calendar sync ------------------------------------------------------------------------------------------
class AsyncCM:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


class Conn:
    def __init__(self, appt):
        self.appt, self.writes = appt, []

    def transaction(self):
        return AsyncCM()

    async def fetchrow(self, sql, *a):
        return self.appt

    async def execute(self, sql, *a):
        self.writes.append((sql, a))


class Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        if self._b == "INVALID":
            raise json.JSONDecodeError("bad", "", 0)
        return self._b


def iso(dt):
    return dt.isoformat()


def canon(appt, remote_id):
    return {"id": remote_id, "status": "confirmed", "start": {"dateTime": iso(appt["starts_at"]), "timeZone": appt["timezone"]},
            "end": {"dateTime": iso(appt["ends_at"]), "timeZone": appt["timezone"]}, "attendees": [{"email": appt["email"]}],
            "extendedProperties": {"private": {"concierge_appointment": appt["id"], "concierge_tenant": appt["tenant_id"]}}}


def mutate(ev, appt, how):
    ev = json.loads(json.dumps(ev))
    if how == "ok":
        return ev
    if how == "email_case":
        ev["attendees"] = [{"email": appt["email"].upper()}]
    elif how == "no_attendee":
        ev["attendees"] = []
    elif how == "no_email_key":
        ev["attendees"] = [{}]
    elif how == "other_attendee":
        ev["attendees"] = [{"email": "someone@else.co"}]
    elif how == "wrong_appt":
        ev["extendedProperties"]["private"]["concierge_appointment"] = "nope"
    elif how == "wrong_tenant":
        ev["extendedProperties"]["private"]["concierge_tenant"] = "nope"
    elif how == "no_ext":
        del ev["extendedProperties"]
    elif how == "cancelled":
        ev["status"] = "cancelled"
    elif how == "start_shift":
        ev["start"]["dateTime"] = iso(appt["starts_at"] + timedelta(hours=1))
    elif how == "end_shift":
        ev["end"]["dateTime"] = iso(appt["ends_at"] + timedelta(minutes=1))
    elif how == "offset_equiv":
        tz = timezone(timedelta(hours=13))
        ev["start"]["dateTime"] = appt["starts_at"].astimezone(tz).isoformat()
        ev["end"]["dateTime"] = appt["ends_at"].astimezone(tz).isoformat()
    elif how == "z_form":
        ev["start"]["dateTime"] = iso(appt["starts_at"]).replace("+00:00", "Z")
        ev["end"]["dateTime"] = iso(appt["ends_at"]).replace("+00:00", "Z")
    elif how == "missing_end":
        del ev["end"]
    elif how == "garbage_time":
        ev["start"]["dateTime"] = "not a time"
    elif how == "invalid_json":
        return "INVALID"
    return ev


HOWS = ["ok"] * 8 + ["email_case", "no_attendee", "no_email_key", "other_attendee", "wrong_appt", "wrong_tenant", "no_ext", "cancelled", "start_shift",
                     "end_shift", "offset_equiv", "z_form", "missing_end", "garbage_time", "invalid_json"]


def spec(status, body=None, err=False):
    return {"status": status, "body": body, "err": err}


calendar_cases = []
for _ in range(900):
    start = datetime(2026, 11, 10, 10, 0, tzinfo=UTC) + timedelta(hours=rng.randint(-30, 400), minutes=rng.choice([0, 15, 30]))
    appt = {"id": "appt-1", "tenant_id": "t-1", "status": rng.choice(["booked"] * 7 + ["cancelled", "no_show", "completed"]),
            "calendar_sync_requested": rng.random() < 0.93, "calendar_state": rng.choice(["pending", "pending", "synced", "retry"]),
            "email": rng.choice(["a@b.co", "a@b.co", "A@B.co", ""]), "consent_contact": rng.random() < 0.9, "name": rng.choice(["Ann", "Zoë"]),
            "notes": rng.choice(["", "bring ID"]), "business_name": rng.choice(["Trendi", "Café Ünï"]), "timezone": rng.choice(["Pacific/Auckland", "UTC"]),
            "starts_at": start, "ends_at": start + timedelta(minutes=rng.choice([15, 30, 60]))}
    cal_id = rng.choice(["owner@gmail.com", "primary", "x y/z@é.co"]) if rng.random() < 0.93 else None
    remote_id = cc.event_id(appt["tenant_id"], appt["id"])
    ev = canon(appt, remote_id)
    sc = {
        "get1": rng.choice([spec(404)] * 8 + [spec(200, mutate(ev, appt, "ok")), spec(200, mutate(ev, appt, rng.choice(HOWS))), spec(500), spec(None, err=True), spec(410)]),
        "busy": rng.choice([spec(200, {"calendars": {cal_id: {"busy": []}}})] * 10 + [spec(200, {"calendars": {cal_id: {"busy": [{"start": "2026-11-10T10:00:00Z", "end": "2026-11-10T11:00:00Z"}]}}})] * 2 + [spec(200, {"calendars": {cal_id: {"busy": [{"start": "2026-11-10T10:00:00Z", "end": "2026-11-10T11:00:00Z"}]}}}),
                                                                                       spec(200, {"calendars": {cal_id: {"errors": [{"reason": "x"}]}}}), spec(200, {"calendars": {}}),
                                                                                       spec(500), spec(200, "INVALID"), spec(None, err=True), spec(200, {"calendars": {cal_id: {"busy": [{"start": "x"}]}}}),
                                                                                       spec(200, {"calendars": {cal_id: {"busy": [{"start": "bad", "end": "worse"}]}}})]),
        "post": rng.choice([spec(201, mutate(ev, appt, "ok"))] * 6 + [spec(201, mutate(ev, appt, rng.choice(HOWS))), spec(200, mutate(ev, appt, rng.choice(HOWS))), spec(409), spec(500), spec(None, err=True)]),
        "get2": rng.choice([spec(200, mutate(ev, appt, rng.choice(HOWS))), spec(404), spec(500)]),
        "delete": rng.choice([spec(200), spec(204), spec(404), spec(410), spec(500), spec(None, err=True)]),
    }
    log, state = [], {"posted": False}

    async def connection(tenant_id, cid=cal_id):
        return {"calendar_id": cid} if cid else None

    async def request(tenant_id, method, path, **kw):
        if method == "DELETE":
            s = sc["delete"]
        elif method == "GET":
            s = sc["get2"] if state["posted"] else sc["get1"]
        elif path.endswith("/freeBusy"):
            s = sc["busy"]
        else:
            state["posted"] = True
            s = sc["post"]
        log.append({"method": method, "path": path, "params": kw.get("params"), "json": kw.get("json"), "resp": s})
        if s["err"]:
            raise httpx.ConnectError("boom")
        return Resp(s["status"], s["body"])

    cc.connection, cc.request = connection, request
    conn = Conn(appt)
    pool = SimpleNamespace(acquire=lambda c=conn: AsyncCM(c))
    db.pool = lambda p=pool: p
    asyncio.run(cc.sync_one(appt["id"]))
    outcome = None
    if conn.writes:
        sql, args = conn.writes[-1]
        outcome = {"state": re.search(r"calendar_state='(\w+)'", sql).group(1), "error": (re.search(r"calendar_error='([^']*)'", sql) or [None, ""])[1],
                   "remote_id": args[1] if "calendar_event_id=$2" in sql else None,
                   "invitation": "provider_requested" if "invitation_state='provider_requested'" in sql else None}
    calendar_cases.append({"appt": {**appt, "starts_at": int(start.timestamp()), "ends_at": int(appt["ends_at"].timestamp())}, "cal": cal_id, "log": log, "outcome": outcome})

print(json.dumps({"sms": sms_cases, "digest": digest_cases, "audio": audio_cases, "calendar": calendar_cases}, ensure_ascii=False, indent=0, default=str))
