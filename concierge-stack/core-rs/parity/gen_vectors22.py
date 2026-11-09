"""Batch-22 golden vectors: `calendar_connection` outside the event state machine: application config, token files, access-token refresh, the OAuth
start/finish/disconnect flows, the booking notice and the worker loop, from the live module with a temporary secret directory, a fake `httpx`
and a fake database. No Google call is made.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors22.py > ../concierge-stack/core-rs/parity/vectors22.json
"""
import asyncio
import hashlib
import json
import random
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import HTTPException

sys.path.insert(0, ".")
from app import automation, calendar_connection as cc, db, tenants  # noqa: E402

rng = random.Random(20261129)
UTC = timezone.utc
CUR = {"now": 1_800_000_000}


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        d = datetime.fromtimestamp(CUR["now"], UTC)
        return d.astimezone(tz) if tz else d.replace(tzinfo=None)


cc.datetime = FixedDT
TID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
out = {}


def read_saved(d):
    p = Path(d) / (TID + ".json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return "UNPARSEABLE"


def call(coro):
    try:
        return {"ok": asyncio.run(coro)}
    except HTTPException as e:
        return {"http": [e.status_code, e.detail]}
    except cc.CalendarUnavailable as e:
        return {"unavailable": str(e)}
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        return {"raises": type(e).__name__}


class CM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


class Resp:
    def __init__(self, status, body):
        self.status_code, self.b = status, body

    def json(self):
        if self.b == "INVALID":
            raise ValueError("bad")
        return self.b


class Client:
    spec = None
    log = []

    def __init__(self, timeout=None):
        Client.log.append(["client", timeout])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    async def post(self, url, data=None):
        Client.log.append(["post", url, data])
        if Client.spec == "error":
            raise httpx.ConnectError("down")
        return Resp(*Client.spec)


cc.httpx.AsyncClient = Client

# ---- application / token_path -----------------------------------------------------------------------------------------------
app_cases = []
APPS = [None, "", "not json", "[]", "{}", json.dumps({"client_id": "a", "client_secret": "b", "redirect_uri": "c"}), json.dumps({"client_id": "a", "client_secret": "", "redirect_uri": "c"}),
        json.dumps({"client_id": "a", "client_secret": "b"}), json.dumps({"client_id": "a", "client_secret": "b", "redirect_uri": "c", "extra": 1}), json.dumps(5)]
for configured in (True, False):
    for text in APPS:
        with tempfile.TemporaryDirectory() as d:
            if text is not None:
                (Path(d) / "google-app.json").write_text(text)
            cc.get_settings = lambda d=d, c=configured: SimpleNamespace(calendar_credentials_dir=d if c else "")
            try:
                r = {"ok": cc.application()}
            except cc.CalendarUnavailable as e:
                r = {"unavailable": str(e)}
            except (AttributeError, TypeError) as e:
                r = {"raises": type(e).__name__}
            app_cases.append({"configured": configured, "text": text, "out": r})
out["application"] = app_cases
paths = []
for t in [TID, TID.upper(), TID.replace("-", ""), "{" + TID + "}", "urn:uuid:" + TID, "x", "", TID + "0", TID[:-1], 5, "3f2504e04f8941d39a0c0305e82c3301", "3f25-04e0-4f89-41d3-9a0c-0305e82c3301"]:
    cc.get_settings = lambda: SimpleNamespace(calendar_credentials_dir="/secrets")
    try:
        paths.append({"in": t, "out": {"ok": str(cc.token_path(t))}})
    except (ValueError, AttributeError) as e:
        paths.append({"in": t, "out": {"raises": type(e).__name__}})
out["token_path"] = paths

# ---- access_token -------------------------------------------------------------------------------------------------------------
tok = []
for case in range(160):
    CUR["now"] = 1_800_000_000
    token_state = rng.choice(["missing", "invalid", "fresh", "fresh_edge", "fresh_half", "fresh_61", "stale", "stale", "no_access", "no_refresh"])
    token = {"access_token": "AT", "refresh_token": "RT", "expires_at": {"fresh": CUR["now"] + 3600, "fresh_edge": CUR["now"] + 60, "fresh_half": CUR["now"] + 60.5, "fresh_61": CUR["now"] + 61, "stale": CUR["now"] + 59, "no_access": CUR["now"] + 3600,
                                                                           "no_refresh": 0}.get(token_state, 0)}
    if token_state == "no_access":
        del token["access_token"]
    if token_state == "no_refresh":
        del token["refresh_token"]
    app_ok = rng.random() < 0.9
    provider = rng.choice([(200, {"access_token": "NEW", "expires_in": 120}), (200, {"access_token": "NEW"}), (200, {}), (400, {}), (200, "INVALID"), "error"])
    with tempfile.TemporaryDirectory() as d:
        if token_state == "invalid":
            (Path(d) / (TID + ".json")).write_text("not json")
        elif token_state != "missing":
            (Path(d) / (TID + ".json")).write_text(json.dumps(token))
        if app_ok:
            (Path(d) / "google-app.json").write_text(json.dumps({"client_id": "a", "client_secret": "b", "redirect_uri": "c"}))
        cc.get_settings = lambda d=d: SimpleNamespace(calendar_credentials_dir=d)
        Client.log, Client.spec = [], provider
        try:
            r = {"ok": asyncio.run(cc.access_token(TID))}
        except cc.CalendarUnavailable as e:
            r = {"unavailable": str(e)}
        except httpx.HTTPError:
            r = {"raises": "HTTPError"}
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            r = {"raises": type(e).__name__}
        saved = read_saved(d)
    tok.append({"token_state": token_state, "token": token, "app_ok": app_ok, "provider": provider, "out": r, "saved": saved, "log": Client.log})
out["access_token"] = tok

# ---- start ------------------------------------------------------------------------------------------------------------------
start = []
for app_ok in (True, False):
  for rep in range(10):
    for state in ["S" * 43, "a-b_c" * 8]:
        with tempfile.TemporaryDirectory() as d:
            if app_ok:
                (Path(d) / "google-app.json").write_text(json.dumps({"client_id": "id & co", "client_secret": "b", "redirect_uri": "https://x.example/cb?a=b c"}))
            cc.get_settings = lambda d=d: SimpleNamespace(calendar_credentials_dir=d)
            cc.secrets.token_urlsafe = lambda n, state=state: state
            eff = []

            class P:
                async def execute(self, sql, *a):
                    eff.append(list(a))

            db.pool = lambda: P()
            role = rng.choice(["owner", "owner", "editor", "viewer"])
            r = call(cc.start({"tenant_id": TID, "id": "u-1", "role": role}))
            start.append({"app_ok": app_ok, "state": state, "role": role, "out": r, "effects": eff})
out["start"] = start

# ---- finish -----------------------------------------------------------------------------------------------------------------
fin = []
SC = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy"
for case in range(200):
    CUR["now"] = 1_800_000_000
    state_found = rng.random() < 0.85
    app_ok = rng.random() < 0.95
    provider = rng.choice([(200, {"scope": SC, "refresh_token": "RT", "access_token": "A", "expires_in": 100}), (200, {"scope": SC, "refresh_token": "RT", "access_token": "A"}),
                           (200, {"scope": SC.split()[0], "refresh_token": "RT"}), (200, {"scope": SC}), (200, {"scope": SC + " extra", "refresh_token": "RT"}), (200, {"refresh_token": "RT"}),
                           (400, {}), (200, "INVALID"), "error"])
    body_state = rng.choice(["s" * 32, "t" * 40])
    role = rng.choice(["owner"] * 6 + ["editor", "viewer"])
    eff = []
    with tempfile.TemporaryDirectory() as d:
        if app_ok:
            (Path(d) / "google-app.json").write_text(json.dumps({"client_id": "a", "client_secret": "b", "redirect_uri": "c"}))
        cc.get_settings = lambda d=d: SimpleNamespace(calendar_credentials_dir=d)
        Client.log, Client.spec = [], provider

        class P2:
            async def fetchval(self, sql, *a):
                eff.append(["delete_state", list(a)])
                return TID if state_found else None

            async def execute(self, sql, *a):
                eff.append(["connect", list(a)])

        db.pool = lambda: P2()
        try:
            r = {"ok": asyncio.run(cc.finish(cc.OAuthFinish(state=body_state, code="CODE"), {"tenant_id": TID, "id": "u-1", "role": role}))}
        except HTTPException as e:
            r = {"http": [e.status_code, e.detail]}
        except cc.CalendarUnavailable as e:
            r = {"unavailable": str(e)}
        except httpx.HTTPError:
            r = {"raises": "HTTPError"}
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            r = {"raises": type(e).__name__}
        saved = read_saved(d)
    fin.append({"role": role, "state_found": state_found, "app_ok": app_ok, "provider": provider, "state": body_state, "out": r, "saved": saved, "log": Client.log, "effects": eff})
out["finish"] = fin
out["finish_model"] = []
for st in ["s" * 31, "s" * 32, "s" * 100, "s" * 101, 5, None]:
    for code in ["", "c", "c" * 4096, "c" * 4097, None]:
        try:
            m = cc.OAuthFinish.model_validate({"state": st, "code": code})
            r = {"ok": m.model_dump()}
        except Exception as e:  # noqa: BLE001
            r = {"errors": [[".".join(map(str, x["loc"])), x["type"]] for x in e.errors()]}
        out["finish_model"].append({"in": {"state": st, "code": code}, "out": r})

# ---- notify_synced and process_once -----------------------------------------------------------------------------------------------
notice = []
for case in range(60):
    row = rng.choice([None, {"id": "ap-1", "tenant_id": "t-1", "lead_id": "l-1"}])
    lead = rng.choice([None, {"id": "l-1", "name": "Pat"}])
    eff = []

    class P3:
        async def fetchrow(self, sql, *a):
            if "FROM appointments" in sql:
                eff.append(["appointment", list(a)])
                return row
            eff.append(["lead", list(a)])
            return lead

        async def execute(self, sql, *a):
            eff.append(["done", list(a)])

    async def gbi(tid):
        eff.append(["tenant", [tid]])
        return {"id": tid}

    async def booked(t, appt, l):
        eff.append(["on_booked", [t, appt, l]])

    db.pool = lambda: P3()
    tenants.get_by_id = gbi
    automation.on_appointment_booked = booked
    asyncio.run(cc.notify_synced("ap-1"))
    notice.append({"row": row, "lead": lead, "effects": eff})
out["notify"] = notice
proc = []
for case in range(40):
    due = [{"id": "a%d" % i} for i in range(rng.choice([0, 1, 3]))]
    pending = [{"id": "n%d" % i} for i in range(rng.choice([0, 1, 2]))]
    eff = []

    class P4:
        async def fetch(self, sql, *a):
            eff.append(["fetch", "sync" if "calendar_attempts<10" in sql else "notices"])
            return due if "calendar_attempts<10" in sql else pending

    async def sync_fake(i):
        eff.append(["sync_one", [i]])

    async def notify_fake(i):
        eff.append(["notify_synced", [i]])

    db.pool = lambda: P4()
    cc.sync_one, cc.notify_synced = sync_fake, notify_fake
    asyncio.run(cc.process_once())
    proc.append({"due": due, "pending": pending, "effects": eff})
out["process"] = proc
json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
