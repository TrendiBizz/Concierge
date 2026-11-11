import asyncio
import time
from types import SimpleNamespace

from app import chat


def _call(name, call_id):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments="{}"))


def test_read_only_tools_run_concurrently(monkeypatch):
    async def slow(tenant, name, args, ctx):
        await asyncio.sleep(0.1)
        return {"ok": True}

    monkeypatch.setattr(chat, "run_tool", slow)
    calls = [_call("search_knowledge", "a"), _call("check_availability", "b")]

    async def scenario():
        start = time.perf_counter()
        results = await chat._execute_tools(calls, {"id": "t"}, {})
        return time.perf_counter() - start, results

    elapsed, results = asyncio.run(scenario())
    assert elapsed < 0.18
    assert len(results) == 2


def test_mutating_tools_stay_sequential(monkeypatch):
    order = []

    async def slow(tenant, name, args, ctx):
        order.append(name)
        await asyncio.sleep(0.05)
        return {"ok": True}

    monkeypatch.setattr(chat, "run_tool", slow)
    calls = [_call("capture_lead", "a"), _call("book_appointment", "b")]

    elapsed = asyncio.run(_timed(chat._execute_tools, calls))
    assert elapsed >= 0.09
    assert order == ["capture_lead", "book_appointment"]


async def _timed(fn, calls):
    start = time.perf_counter()
    await fn(calls, {"id": "t"}, {})
    return time.perf_counter() - start
