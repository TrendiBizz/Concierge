"""Batch-16 golden vectors: one conversation turn (`chat.run_turn`) from the live module, with a scripted model, scripted tools and a
recording fake environment. Nothing is sent and no network is used.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors16.py > ../concierge-stack/core-rs/parity/vectors16.json
"""
import asyncio
import copy
import json
import os
import random
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import chat, convo, db, enquiries, llm, owner_notifications, rag  # noqa: E402

rng = random.Random(20261123)
UTC = timezone.utc
FIXED = datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC)


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


rag.datetime = FixedDT

TENANTS = [
    {"id": "t-1", "name": "Trendi", "persona": "Friendly.", "incentive": "10% off, was $100", "native_booking": True, "booking_url": "https://x.test/book", "timezone": "Pacific/Auckland",
     "business_hours": {"mon": [["09:00", "17:00"]]}, "sms_enabled": True, "voice_enabled": True},
    {"id": "t-2", "name": "Café Ünï", "persona": None, "incentive": None, "native_booking": False, "booking_url": None, "timezone": "UTC", "business_hours": None, "sms_enabled": False},
    {"id": "t-3", "name": "Bare", "persona": "", "incentive": "", "timezone": ""},
]
HITS = [[], [{"title": "Prices", "url": "https://x.test/p", "content": "Basic plan $50 per month. Setup $1,200.50"}],
        [{"title": "", "url": "https://x.test/q", "content": "We open at 9."}, {"title": "FAQ", "url": "http://x.test", "content": "Ünï é"}]]
REPLIES = ["It was $100 before.", "Hello there!", "  padded reply \n", "The basic plan is $50 per month.", "That costs $999.", "It is $50 or $1,200.50.", "", "   ", "Only $5 today", "Free of charge"]
TOOLS = ["capture_lead", "search_knowledge", "book_appointment", "request_enquiry_acknowledgement"]
RESULTS = [{"ok": True, "note": "x"}, {"ok": False, "error": "é \"quoted\""}, {"results": ["$50 fee", "b"]}, {"n": 3, "none": None}, "plain string", ["l", 1, True]]
UPDATES = [{}, {}, {"tool_results": ["Price is $120"]}, {"lead_captured": True}, {"booking_url": "https://b.test/x"}, {"appointment_text": "Mon 9am"}, {"tool_calls": ["capture_lead"]}]


def mk_msg(content, calls):
    return SimpleNamespace(content=content, tool_calls=[SimpleNamespace(id=c["id"], function=SimpleNamespace(name=c["name"], arguments=c["arguments"])) for c in calls])


out = []
for case in range(260):
    tenant = copy.deepcopy(rng.choice(TENANTS))
    channel = rng.choice(["chat", "chat", "sms", "email", "voice", "phone", "other"])
    hits = rng.choice(HITS)
    rounds = []
    for _ in range(rng.choice([1, 1, 1, 2, 3, 5])):
        if len(rounds) < 4 and rng.random() < 0.45:
            calls = [{"id": "c%d" % rng.randint(1, 99), "name": rng.choice(TOOLS), "arguments": rng.choice(['{"a": 1}', "{}", "", None, "not json", '{"q": "é"}', "[1]"])}
                     for _ in range(rng.randint(1, 3))]
            rounds.append({"content": rng.choice([None, "thinking", ""]), "calls": calls})
        else:
            rounds.append({"content": rng.choice(REPLIES), "calls": []})
    retry = {"content": rng.choice(REPLIES), "calls": []}
    tool_script = [{"result": rng.choice(RESULTS), "update": rng.choice(UPDATES)} for _ in range(40)]
    history = [{"role": rng.choice(["user", "assistant"]), "content": "h%d" % i} for i in range(rng.choice([0, 2, 5]))]
    dialogue = [{"role": rng.choice(["user", "assistant"]), "content": rng.choice(["a", "é", "b\nc"])} for _ in range(rng.choice([1, 3]))]
    args = {
        "session_id": rng.choice(["s" * 10, "sess-é"]), "message": rng.choice(["Hi", "How much?", "So it's $1, right?", "é" * 20]),
        "page_url": rng.choice([None, "", "https://p.test/a"]), "utm": rng.choice([None, {}, {"utm_source": "g", "x": "y"}, {"utm_a": 5, "utm_b": "é"}]),
        "sender_phone": rng.choice([None, "+64211234567"]), "sender_email": rng.choice([None, "", "a@b.co"]), "dry_run": rng.random() < 0.2,
    }
    lead = rng.choice([None, "lead-9"])
    effects, llm_script, tool_i = [], list(rounds) + [retry], {"i": 0, "t": 0}

    async def get_or_create(t, session, ch, page, utm):
        effects.append(["get_or_create", [t["id"], session, ch, page, utm]])
        return "conv-1"

    async def save_message(cid, role, content, flag=None):
        effects.append(["save", [cid, role, content, flag]])

    async def capture(t, ch, source, message, **kw):
        effects.append(["capture", [t["id"], ch, source, message, {k: str(v) for k, v in kw.items()}]])

    async def history_fn(cid):
        effects.append(["history", [cid]])
        return history

    async def retrieve(tid, message):
        effects.append(["retrieve", [tid, message]])
        return hits

    async def complete(messages, tools=None, temperature=0.3, max_tokens=600):
        effects.append(["llm", [copy.deepcopy(messages), tools]])
        r = llm_script[min(tool_i["i"], len(llm_script) - 1)]
        tool_i["i"] += 1
        return mk_msg(r["content"], r["calls"])

    async def run_tool(t, name, a, ctx):
        s = tool_script[tool_i["t"]]
        tool_i["t"] += 1
        effects.append(["tool", [name, a, json.loads(json.dumps(ctx, default=str)), s["result"], s["update"]]])
        ctx.update(copy.deepcopy(s["update"]))
        return s["result"]

    class Pool:
        async def fetch(self, sql, *a):
            effects.append(["dialogue", list(a)])
            return dialogue

        async def fetchval(self, sql, *a):
            effects.append(["lead", list(a)])
            return lead

    async def queue(t, subject, body, dedupe, lead_id=None):
        effects.append(["owner", [t["id"], subject, body, dedupe, lead_id]])

    convo.get_or_create, convo.save_message, enquiries.capture = get_or_create, save_message, capture
    chat._history, chat.retrieve, chat.llm.complete, chat.run_tool = history_fn, retrieve, complete, run_tool
    db.pool = lambda: Pool()
    owner_notifications.queue = queue
    res = asyncio.run(chat.run_turn(tenant, args["session_id"], channel, args["message"], page_url=args["page_url"], utm=args["utm"], sender_phone=args["sender_phone"],
                                    sender_email=args["sender_email"], dry_run=args["dry_run"]))
    out.append({"tenant": tenant, "channel": channel, "hits": hits, "rounds": rounds, "retry": retry, "tool_script": tool_script, "history": history, "dialogue": dialogue,
                "lead": lead, "args": args, "now": int(FIXED.timestamp()), "out": res, "effects": effects})

json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
