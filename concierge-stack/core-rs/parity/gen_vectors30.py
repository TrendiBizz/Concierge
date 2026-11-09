"""Batch-30 golden vectors: the response shapes of the read-only admin listing routes (`app.main` + `scoring`, `sla`, `sales`).

Every expected body is the output of the LIVE handler (`main.admin_scoring`, `main.admin_sla`, `main.admin_get_campaign`,
`main.admin_list_campaigns`, `main.admin_pipeline`, `main.admin_sales_summary`, `main._stats`) encoded the way FastAPI encodes it
(`jsonable_encoder`, then the compact `json.dumps` that `JSONResponse` uses). Only the database is stubbed: a pool whose
`fetch`/`fetchval`/`fetchrow` answer by SQL fragment with canned rows. The Rust tests are handed the same rows in the shape
`row_json` produces (`jsonable_encoder` of the same Python rows) and must reproduce the body byte for byte.
A case where the live function raises (FastAPI answers a plain 500) records `"error": true`.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors30.py > ../concierge-stack/core-rs/parity/vectors30.json
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from fastapi.encoders import jsonable_encoder  # noqa: E402

from app import main  # noqa: E402

NOW = datetime(2026, 11, 9, 12, 0, 0, 123456, tzinfo=timezone.utc)


def enc(x):
    return jsonable_encoder(x)


def body(x):
    return json.dumps(enc(x), ensure_ascii=False, separators=(",", ":"))


class FakePool:
    def __init__(self, answers):
        self.answers = answers  # list of (sql fragment, rows)

    def _rows(self, sql):
        for fragment, rows in self.answers:
            if fragment in sql:
                return rows
        raise AssertionError(f"unanswered SQL: {sql[:80]}")

    async def fetch(self, sql, *args):
        return list(self._rows(sql))

    async def fetchval(self, sql, *args):
        return self._rows(sql)

    async def fetchrow(self, sql, *args):
        rows = self._rows(sql)
        return rows[0] if rows else None


def live(coro_fn, tenant, answers, *args):
    async def get_by_slug(slug):
        return tenant

    main.tenants.get_by_slug = get_by_slug
    main.db.pool = lambda: FakePool(answers)
    try:
        return {"out": body(asyncio.run(coro_fn(*args)))}
    except Exception:  # noqa: BLE001 - a 500 in production
        return {"error": True}


def tenant(**over):
    t = {"id": uuid.UUID("00000000-0000-0000-0000-000000000001"), "name": "Open Co", "sla_minutes": 0,
         "sla_min_score": None, "lead_value_cents": 0, "scoring": None}
    t.update(over)
    return t


cases = []

# ---------------------------------------------------------------- scoring.describe
SCORING = [None, "", "{}", '{"warm_at": 20}', '{"phone": "x"}', '{"phone": true}', '{"phone": null}', '{"phone": 1.5, "zzz": 3}',
           '{"phone": [1, {"a": "é"}]}', "[]", "5", "null", "not json", '"str"', '{"hot_at": 80, "warm_at": 10, "email": -7}',
           {"hot_at": 80}, {}, [], 5, True, '{"PHONE": 3}', '{"phone": 0}', '{"phone": -50, "email": 50}', '{"phone": 1e2}',
           '{"phone": 1.0}', '{"phone": {"a": 1}}', '{"warm_at": "ünï"}']
for s in SCORING:
    r = live(main.admin_scoring, tenant(scoring=s), [], "any")
    cases.append({"kind": "scoring", "scoring": s, **r})


# ---------------------------------------------------------------- sla
def lead(i, **over):
    row = {"id": uuid.UUID(int=i), "name": f"Lead {i}", "phone": "+64 21 555 0000", "email": "a@b.example", "message": "hi",
           "channel": "chat", "score": 80, "score_label": "hot", "score_reasons": '["gave a phone number", "asked for a price"]',
           "created_at": NOW - timedelta(minutes=90, microseconds=i), "sla_alerted_at": None, "minutes_waiting": 90}
    row.update(over)
    return row


SLA_ROWS = [
    [],
    [lead(1)],
    [lead(1), lead(2, name="Ünï <b> & \"q\"", score_reasons="[]", sla_alerted_at=NOW, minutes_waiting=0)],
    [lead(3, name=None, phone=None, email=None, message=None, channel=None, score_label=None, score_reasons=None)],
    [lead(4, score_reasons="not json"), lead(5, score_reasons='{"a": 1}'), lead(6, score_reasons='"text"'),
     lead(7, score_reasons="null"), lead(8, score_reasons='["é", 1, null, {"k": [1, 2]}]'), lead(9, score_reasons=["already", "a list"]),
     lead(10, score_reasons=""), lead(11, score_reasons="5")],
    [lead(12, created_at=NOW.replace(microsecond=0)), lead(13, created_at=NOW.replace(microsecond=1))],
]
for t in (tenant(sla_minutes=30), tenant(sla_minutes=30, sla_min_score=0), tenant(sla_minutes=30, sla_min_score=55),
          tenant(sla_minutes=0), tenant(sla_minutes=None), tenant(sla_minutes=-5, sla_min_score=10), tenant(sla_minutes=1, sla_min_score=100)):
    for rows in SLA_ROWS:
        r = live(main.admin_sla, t, [("minutes_waiting", rows)], "any")
        cases.append({"kind": "sla", "tenant": enc(t), "rows": enc(rows), **r})


# ---------------------------------------------------------------- campaigns (view + delivery)
def campaign(i, **over):
    row = {"id": i, "tenant_id": uuid.UUID(int=99), "name": f"Camp {i}", "channel": "sms", "subject": "", "body": "Hi {first}",
           "filters": '{"statuses": ["new", "lost"], "min_score": 0, "older_than_days": 30}', "status": "draft",
           "recipient_count": 0, "created_at": NOW, "queued_at": None}
    row.update(over)
    return row


FILTERS = ['{"statuses": ["new", "lost"], "min_score": 0, "older_than_days": 30}', "{}", "[]", "null", "5", '"x"', "1.5", "not json",
           '{"name": "é中 <b>", "n": [1, 2.5, null, true]}', "", {"already": "decoded"}, None, '{"max_recipients": 10}',
           '{"deep": {"a": {"b": [1, {"c": "d"}]}}}', '{"f": 1.0}']
DELIVERY = [[], [{"status": "sent", "n": 3}], [{"status": "sent", "n": 3}, {"status": "failed", "n": 1}, {"status": "pending", "n": 12}]]
for f in FILTERS:
    for d in DELIVERY:
        c = campaign(7, filters=f, queued_at=NOW if d else None, status="queued" if d else "draft")

        async def fake_get(campaign_id, c=c):
            return dict(c)

        main.campaigns.get = fake_get
        r = live(main.admin_get_campaign, tenant(), [("FROM outbox", d), ("FROM tenants", [tenant()])], 7)
        cases.append({"kind": "campaign", "campaign": enc(c), "delivery": [[x["status"], x["n"]] for x in d], **r})
        rl = live(main.admin_list_campaigns, tenant(), [("FROM campaigns", [campaign(7, filters=f), campaign(8)]), ("FROM outbox", d)], "any")
        cases.append({"kind": "campaign_list", "campaigns": enc([campaign(7, filters=f), campaign(8)]),
                      "delivery": [[x["status"], x["n"]] for x in d], **rl})


# ---------------------------------------------------------------- pipeline
def pl(i, **over):
    row = {"id": uuid.UUID(int=i), "name": f"P{i}", "phone": "", "email": "", "message": "m", "channel": "chat", "status": "new",
           "score": 10, "score_label": "cold", "value_cents": 0, "next_action_at": None, "lost_reason": "", "won_at": None,
           "lost_at": None, "created_at": NOW}
    row.update(over)
    return row


PIPE = [
    [],
    [pl(1)],
    [pl(1, status="new", value_cents=1000), pl(2, status="contacted", value_cents=0), pl(3, status="booked", value_cents=333),
     pl(4, status="won", value_cents=5000, won_at=NOW), pl(5, status="lost", lost_reason="é <b>", lost_at=NOW)],
    [pl(1, status="weird"), pl(2, status="", value_cents=7), pl(3, status=None)],
    [pl(i, status="new", value_cents=i) for i in range(1, 8)],
    [pl(1, status="contacted", value_cents=1), pl(2, status="contacted", value_cents=1), pl(3, status="new", value_cents=1)],
]
for avg in (0, 1, 2500, 12345):
    for rows in PIPE:
        t = tenant(lead_value_cents=avg)
        r = live(main.admin_pipeline, t, [("FROM leads", rows)], "any")
        cases.append({"kind": "pipeline", "average": avg, "rows": enc(rows), **r})
t = tenant(lead_value_cents=None)
cases.append({"kind": "pipeline", "average": 0, "rows": [], **live(main.admin_pipeline, t, [("FROM leads", [])], "any")})

# ---------------------------------------------------------------- sales summary
MOVED = [[], [("contacted", 2)], [("lost", 1)], [("contacted", 5), ("booked", 3), ("lost", 2), ("won", 1)], [("lost", 3)]]
WON = [[], [0], [1000], [0, 0, 500], [1, 2, 3], [999999], [0] * 7]
for avg in (0, 4000):
    for moved in MOVED:
        for won in WON:
            for sla_min, waiting in ((0, []), (None, []), (30, [lead(1)]), (30, []), (-1, [lead(2)]), (30, [lead(1), lead(2), lead(3)])):
                t = tenant(lead_value_cents=avg, sla_minutes=sla_min)
                answers = [
                    ("count(*) FROM leads", 11),
                    ("FROM lead_events", [{"to_status": s, "n": n} for s, n in moved]),
                    ("SELECT value_cents FROM leads", [{"value_cents": v} for v in won]),
                    ("status NOT IN", PIPE[2]),
                    ("minutes_waiting", waiting),
                    ("FROM tasks", 4),
                ]
                r = live(main.admin_sales_summary, t, answers, "any", 7)
                cases.append({"kind": "summary", "days": 7, "average": avg, "moved": [list(m) for m in moved], "won": won,
                              "sla_minutes": sla_min, "waiting": (len(waiting) if sla_min > 0 else 0) if sla_min else None, "new_leads": 11, "overdue_todos": 4, **r})


# ---------------------------------------------------------------- stats
def stats_case(days, convs, statuses, appts, guard, sent, daily, avg, won_value):
    t = tenant(lead_value_cents=avg)
    answers = [
        ("count(*) AS conversations", [{"channel": c, "conversations": n} for c, n in convs]),
        ("count(*) AS n FROM leads", [{"status": s, "n": n} for s, n in statuses]),
        ("FROM appointments", appts),
        ("FROM messages m", guard),
        ("FROM outbox", [{"channel": c, "n": n} for c, n in sent]),
        ("generate_series", [{"day": datetime(2026, 11, 9 - i).date(), "conversations": c, "leads": l} for i, (c, l) in enumerate(daily)]),
        ("sum(value_cents)", won_value),
    ]
    r = asyncio.run(_stats(t, answers, days))
    return {"kind": "stats", "days": r.get("days"), "convs": [list(x) for x in convs], "statuses": [list(x) for x in statuses],
            "appointments": appts, "guard": guard, "sent": [list(x) for x in sent],
            "daily": [[(datetime(2026, 11, 9 - i).date()).isoformat(), c, l] for i, (c, l) in enumerate(daily)],
            "average": avg, "won_value": won_value, "out": body(r)}


async def _stats(t, answers, days):
    main.db.pool = lambda: FakePool(answers)
    return await main._stats(t, days)


for days in (1, 7, 30, 365, 366, 0, -3, 10 ** 24):
    for convs, statuses in (([], []), ([("chat", 4)], [("new", 1)]), ([("chat", 3), ("sms", 4)], [("new", 2), ("won", 1), ("lost", 4)]),
                            ([("chat", 3)], [("new", 1)]), ([("chat", 7)], [("new", 2)]), ([("chat", 9)], [("new", 2)]), ([], [("new", 5)]),
                            ([("chat", 1)], [("new", 200)])):
        for avg in (0, 15000):
            daily = [(1, 2), (0, 0), (3, 1)]
            cases.append(stats_case(days, convs, statuses, 3, 1, [("sms", 2), ("email", 5)], daily, avg, 2500))
cases.append(stats_case(30, [("chat", 3)], [("new", 1)], 0, 0, [], [], 0, 0))
cases.append(stats_case(30, [("é中", 1), ("<b>", 2)], [("won", 1), ("é", 1)], 0, 0, [("é", 1)], [(1, 1)], 100, 0))

json.dump({"summary_pipeline_rows": enc(PIPE[2]), "cases": cases}, sys.stdout, ensure_ascii=False)
