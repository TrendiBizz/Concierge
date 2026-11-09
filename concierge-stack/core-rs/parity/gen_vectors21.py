"""Batch-21 golden vectors: `booking.availability` and `booking.book` (read-back, duplicate detection, race-safe booking) from the live module
with a fixed clock, a fake database and a fake calendar provider. No calendar event is created and nothing is sent.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors21.py > ../concierge-stack/core-rs/parity/vectors21.json
"""
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, ".")
from app import booking, calendar_connection, convo, db  # noqa: E402

rng = random.Random(20261128)
UTC = timezone.utc
CUR = {}


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        d = datetime.fromtimestamp(CUR["now"], UTC)
        return d.astimezone(tz) if tz else d.replace(tzinfo=None)


booking.datetime = FixedDT
booking.get_settings = lambda: SimpleNamespace(default_country_code="1")


class CM:
    def __init__(self, v=None):
        self.v = v

    async def __aenter__(self):
        return self.v

    async def __aexit__(self, *e):
        return False


def iso(x):
    return x.isoformat() if isinstance(x, datetime) else x


TZS = ["Pacific/Auckland", "UTC", "America/New_York", "Europe/London", "Asia/Kolkata"]
HOURS = [{"mon": [["09:00", "17:00"]], "tue": [["09:00", "12:00"], ["13:00", "17:00"]], "wed": [["09:00", "17:00"]], "thu": [["09:00", "17:00"]], "fri": [["09:00", "15:00"]],
          "sat": [["10:00", "12:00"]]}, {d: [["00:00", "23:00"]] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}, {"sun": [["01:30", "03:30"]]}, {}]


def mk_tenant():
    return {"id": "t-1", "timezone": rng.choice(TZS), "slot_minutes": rng.choice([15, 30, 60]), "min_notice_hours": rng.choice([0, 2, 24]), "max_days_ahead": rng.choice([7, 30]),
            "business_hours": rng.choice(HOURS[:2] + HOURS[:1] + HOURS), "lead_webhook_url": rng.choice([None, "https://w.example"]), "name": "Acme"}


def rand_now():
    return int(datetime(2026, rng.randint(1, 12), rng.randint(1, 28), 0, tzinfo=UTC).timestamp()) + rng.randint(0, 86399)


def mkrows(tenant, day_ts):
    out = []
    for _ in range(rng.choice([0, 0, 1, 3])):
        s = datetime.fromtimestamp(day_ts + rng.randint(-20, 40) * 1800, UTC)
        out.append([s.isoformat(), (s + timedelta(minutes=tenant["slot_minutes"])).isoformat()])
    return out


def parse_rows(rows):
    return [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in rows]


# ---- availability -----------------------------------------------------------------------------------------------------------
avail = []
for case in range(400):
    CUR["now"] = rand_now()
    t = mk_tenant()
    tz_today = datetime.fromtimestamp(CUR["now"], UTC).astimezone(__import__("zoneinfo").ZoneInfo(t["timezone"])).date()
    off = rng.choice([-1, 0, 0, 1, 2, 3, 5, t["max_days_ahead"], t["max_days_ahead"] + 1, 40])
    ds = (tz_today + timedelta(days=off)).isoformat()
    ds = rng.choice([ds] * 14 + [" " + ds + " ", "", None, "2026-13-01", "2026-02-30", "nope", "20261105", "2026-W45-3", "2026/11/05", "٢٠٢٦-١١-٠٥", ds + "T00:00"])
    base_rows = mkrows(t, CUR["now"])
    busy_rows = mkrows(t, CUR["now"])
    eff = []

    class Pool:
        async def fetch(self, sql, *a):
            eff.append(["booked", [a[0], iso(a[1]), iso(a[2])]])
            return [{"starts_at": s, "ends_at": e} for s, e in parse_rows(base_rows)]

    async def busy(tid, s, e):
        eff.append(["busy", [tid, iso(s), iso(e)]])
        return parse_rows(busy_rows)

    db.pool = lambda: Pool()
    calendar_connection.busy = busy
    r = asyncio.run(booking.availability(t, ds))
    avail.append({"now": CUR["now"], "tenant": t, "date": ds, "booked": base_rows, "busy": busy_rows, "out": r, "effects": eff})

# ---- book -----------------------------------------------------------------------------------------------------------------
books = []
NAMES = ["Alex Doe"] * 9 + ["Alex Doe", "  Alex Doe  ", "", "   ", "É" * 130, None, 7]
PHONES = ["021 123 4567"] * 5 + ["+12111234567"] * 3 + ["021 123 4567", "+64211234567", "", "x", None, "12", "0" * 50]
EMAILS = ["a@b.co"] * 4 + ["a@b.co", "", "bad", "A@B.CO", " a@b.co "]
for case in range(900):
    CUR["now"] = rand_now()
    t = mk_tenant()
    ZI = __import__("zoneinfo").ZoneInfo(t["timezone"])
    local_now = datetime.fromtimestamp(CUR["now"], UTC).astimezone(ZI)
    day = local_now.date() + timedelta(days=rng.choice([0, 1, 2, 3, 4]))
    # prefer a slot that exists
    probe = booking.day_slots(t, day, datetime.fromtimestamp(CUR["now"], UTC), [])
    if probe and rng.random() < 0.92:
        st = rng.choice(probe).astimezone(ZI).strftime("%Y-%m-%d %H:%M")
    else:
        st = rng.choice([f"{day.isoformat()} {rng.randint(0, 23):02d}:{rng.choice(['00', '30', '15'])}", "garbage", "", None, "2026-11-05T14:30:00+13:00", "2026-11-05T14:30Z", "2026-03-08 02:30",
                         "2026-09-27 02:30", "2026-11-01 01:30", "2026-11-05"])
    args = {"start": st, "name": rng.choice(NAMES), "phone": rng.choice(PHONES), "email": rng.choice(EMAILS), "notes": rng.choice(["", "bring ID", None, "n" * 600]),
            "consent_to_contact": rng.choice([True, False, None]), "confirmed": rng.choice([True] * 7 + [False, None, "yes"])}
    for k in list(args):
        if args[k] is None and rng.random() < 0.5:
            del args[k]
    ctx = {"conversation_id": rng.choice(["c-1"] * 8 + [None, ""]), "sender_phone": rng.choice([None, "+64277777777"]), "sms_inbound": rng.choice([True, False]),
           "dry_run": rng.random() < 0.06, "channel": rng.choice(["chat", "sms"]), "page_url": rng.choice([None, "https://p"]), "utm": rng.choice([None, {}, {"utm_a": "b"}])}
    previous = rng.choice([None] * 6 + [{"status": "booked", "name": "Alex Doe", "email": "a@b.co", "phone": "+12111234567", "id": "ap-0", "starts_at": None, "calendar_state": "synced",
                                       "invitation_state": "sent"},
                           {"status": "cancelled", "name": "Alex Doe", "email": "", "phone": "", "id": "ap-0", "starts_at": None},
                           {"status": "booked", "name": "Other Person", "email": "a@b.co", "phone": "+12111234567", "id": "ap-0", "starts_at": None},
                           {"status": "booked", "name": "Alex Doe", "email": "other@b.co", "phone": "+12111234567", "id": "ap-0", "starts_at": None},
                           {"status": "booked", "name": "Alex Doe", "email": "a@b.co", "phone": "+12111234567", "id": "ap-0", "starts_at": None, "calendar_state": "synced"}])
    # make "previous" sometimes consistent with this request
    pending_mode = rng.choice(["match", "match", "match", "none", "other"])
    taken_in_txn = rng.random() < 0.06
    existing_lead = rng.choice([None, {"id": "lead-0"}])
    refetched = rng.choice([{"calendar_state": "synced", "invitation_state": "sent"}, {"calendar_state": "unconnected", "invitation_state": "pending"}, {}])
    base_rows = mkrows(t, CUR["now"])
    busy_rows = mkrows(t, CUR["now"])
    eff = []
    state = {"txn": False, "slot_checks": 0}

    class Conn:
        def transaction(self):
            state["txn"] = True
            return CM()

        async def execute(self, sql, *a):
            eff.append(["lock", list(a)])

        async def fetch(self, sql, *a):
            eff.append(["booked", [a[0], iso(a[1]), iso(a[2]), "txn"]])
            rows = parse_rows(base_rows)
            if taken_in_txn:
                rows = rows + [(datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC))]
            return [{"starts_at": s, "ends_at": e} for s, e in rows]

        async def fetchrow(self, sql, *a):
            if "FROM leads" in sql:
                eff.append(["select_lead", list(a)])
                return existing_lead
            if "INSERT INTO leads" in sql:
                eff.append(["insert_lead", [iso(x) for x in a]])
                return {"id": "lead-1"}
            if "INSERT INTO appointments" in sql:
                eff.append(["insert_appointment", [iso(x) for x in a]])
                return {"id": "appt-1", "starts_at": a[3], "name": a[5], "phone": a[6], "email": a[7]}
            raise AssertionError(sql)

    class Pool:
        def acquire(self):
            return CM(Conn())

        async def fetch(self, sql, *a):
            eff.append(["booked", [a[0], iso(a[1]), iso(a[2])]])
            return [{"starts_at": s, "ends_at": e} for s, e in parse_rows(base_rows)]

        async def fetchrow(self, sql, *a):
            if "conversation_id=$2 AND starts_at=$3" in sql:
                eff.append(["previous", [a[0], a[1], iso(a[2])]])
                if previous is None:
                    return None
                p = dict(previous)
                p["starts_at"] = a[2]
                return p
            eff.append(["refetch", [a[0], a[1]]])
            return {"id": "appt-1", "starts_at": CUR.get("start") or datetime(2026, 1, 1, tzinfo=UTC), **refetched}

    async def busy(tid, s, e):
        eff.append(["busy", [tid, iso(s), iso(e)]])
        return parse_rows(busy_rows)

    async def get_pending(cid):
        eff.append(["get_pending", [cid]])
        return CUR.get("pending")

    async def set_pending(cid, value):
        eff.append(["set_pending", [cid, value]])

    async def sync_one(aid):
        eff.append(["sync_one", [aid]])

    async def notify(aid):
        eff.append(["notify_synced", [aid]])

    db.pool = lambda: Pool()
    calendar_connection.busy, calendar_connection.sync_one, calendar_connection.notify_synced = busy, sync_one, notify
    convo.get_pending_booking, convo.set_pending_booking = get_pending, set_pending
    CUR["pending"] = None
    CUR["start"] = None
    if pending_mode != "none":
        # derive the key the function will compute, using the real code path once
        try:
            local = booking._parse_local(str(args.get("start") or ""))
            su = local.replace(tzinfo=ZI).astimezone(UTC)
            nm = str(args.get("name") or "").strip()[:120]
            from app.contact import is_email, normalize_phone
            ph = normalize_phone(str(args.get("phone") or ctx.get("sender_phone") or "").strip()[:40], "1") or ""
            em = str(args.get("email") or "").strip()[:200]
            cons = bool(args.get("consent_to_contact")) or bool(ctx.get("sms_inbound"))
            key = {"start": su.isoformat(), "name": nm.lower(), "email": em.lower(), "phone": ph, "consent": cons}
            CUR["pending"] = key if pending_mode == "match" else {**key, "name": "someone else"}
            CUR["start"] = su
        except Exception:  # noqa: BLE001
            pass
    ctx_before = json.loads(json.dumps(ctx))
    try:
        r = {"ok": asyncio.run(booking.book(t, args, ctx))}
    except Exception as e:  # noqa: BLE001
        r = {"raises": type(e).__name__}
    books.append({"now": CUR["now"], "tenant": t, "args": args, "ctx0": ctx_before, "previous": previous, "pending": CUR["pending"], "taken": taken_in_txn,
                  "existing_lead": existing_lead, "refetched": refetched, "booked": base_rows, "busy": busy_rows, "start_utc": iso(CUR["start"]), "out": r, "ctx": ctx, "effects": eff})
json.dump({"availability": avail, "book": books}, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
