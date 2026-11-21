"""Regression tests for C2 reliability fixes:

1. Postgres container memory budget in scripts/vps/compose.yml is self-consistent
   (shared_buffers and total worst-case memory stay well under mem_limit).
2. FastAPI lifespan awaits every background worker — including missed_worker and
   insights_worker — before closing the database pool.
3. .github/workflows/uptime.yml no longer probes the retired crm.trendibizz.com host.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app import (
    calendar_connection,
    call_insights,
    db,
    email_secretary,
    main,
    missed_calls,
    outbox,
    sales,
    sla,
    tenants,
    voice_records,
)

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "scripts" / "vps" / "compose.yml"
UPTIME_PATH = ROOT / ".github" / "workflows" / "uptime.yml"

_SIZE_RE = re.compile(r"^\s*(\d+)\s*([kmgt]i?b?)\s*$", re.IGNORECASE)


def _to_mib(raw: str) -> float:
    match = _SIZE_RE.match(raw)
    assert match, f"unparseable memory size: {raw!r}"
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("k", "kb", "kib"):
        return value / 1024.0
    if unit in ("m", "mb", "mib"):
        return value
    if unit in ("g", "gb", "gib"):
        return value * 1024.0
    if unit in ("t", "tb", "tib"):
        return value * 1024.0 * 1024.0
    raise AssertionError(f"unsupported unit {unit!r} in {raw!r}")


def _postgres_block() -> str:
    text = COMPOSE_PATH.read_text()
    match = re.search(r"^  postgres:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "postgres service block not found in scripts/vps/compose.yml"
    return match.group(1)


def _pg_setting(block: str, key: str) -> str:
    match = re.search(rf"-\s*{re.escape(key)}=([^\s#]+)", block)
    assert match, f"postgres setting {key!r} missing from compose.yml"
    return match.group(1)


def test_postgres_memory_settings_fit_within_container_mem_limit():
    block = _postgres_block()

    mem_match = re.search(r"^\s*mem_limit:\s*([^\s#]+)", block, re.MULTILINE)
    assert mem_match, "postgres mem_limit missing from compose.yml"
    mem_limit_mib = _to_mib(mem_match.group(1))

    shm_match = re.search(r"^\s*shm_size:\s*([^\s#]+)", block, re.MULTILINE)
    assert shm_match, "postgres shm_size missing from compose.yml"
    shm_size_mib = _to_mib(shm_match.group(1))

    shared_buffers_mib = _to_mib(_pg_setting(block, "shared_buffers"))
    effective_cache_mib = _to_mib(_pg_setting(block, "effective_cache_size"))
    work_mem_mib = _to_mib(_pg_setting(block, "work_mem"))
    maintenance_work_mem_mib = _to_mib(_pg_setting(block, "maintenance_work_mem"))
    wal_buffers_mib = _to_mib(_pg_setting(block, "wal_buffers"))
    max_connections = int(_pg_setting(block, "max_connections"))

    assert mem_limit_mib >= 512, f"postgres mem_limit ({mem_limit_mib} MiB) is too small"
    assert shm_size_mib >= 128, f"postgres shm_size ({shm_size_mib} MiB) is too small"
    assert shared_buffers_mib < mem_limit_mib, (
        f"shared_buffers ({shared_buffers_mib} MiB) exceeds mem_limit ({mem_limit_mib} MiB)"
    )
    assert shared_buffers_mib <= mem_limit_mib * 0.35, (
        f"shared_buffers ({shared_buffers_mib} MiB) should be <= 35% of mem_limit ({mem_limit_mib} MiB)"
    )
    assert effective_cache_mib <= mem_limit_mib, (
        f"effective_cache_size ({effective_cache_mib} MiB) exceeds mem_limit ({mem_limit_mib} MiB)"
    )

    budget_mib = shared_buffers_mib + maintenance_work_mem_mib + wal_buffers_mib + (max_connections * work_mem_mib)
    assert budget_mib < mem_limit_mib, (
        f"combined Postgres memory budget ({budget_mib:.1f} MiB) exceeds mem_limit ({mem_limit_mib:.1f} MiB)"
    )


@pytest.mark.parametrize(
    "slow_worker",
    ("outbox", "sla", "sales", "missed_calls", "call_insights", "email_secretary", "calendar"),
)
def test_lifespan_awaits_every_worker_before_db_close(monkeypatch, slow_worker):
    async def scenario():
        events: list[str] = []
        db_closed = False
        started: set[str] = set()
        worker_names = ("outbox", "sla", "sales", "missed_calls", "call_insights", "email_secretary", "calendar")

        def make_worker(name: str):
            async def _run(stop: asyncio.Event):
                started.add(name)
                await stop.wait()
                # Only slow_worker lingers during shutdown; if lifespan fails to await it,
                # db.close() runs and lifespan exits while this task is still pending.
                if name == slow_worker:
                    await asyncio.sleep(0.05)
                assert not db_closed, f"{name} worker finished AFTER db.close() was called"
                events.append(f"stopped:{name}")

            return _run

        async def _fake_close():
            nonlocal db_closed
            db_closed = True
            events.append("db:close")

        monkeypatch.setattr(main.settings, "outbox_enabled", True)
        monkeypatch.setattr(db, "init", AsyncMock())
        monkeypatch.setattr(db, "close", _fake_close)
        monkeypatch.setattr(tenants, "ensure_report_tokens", AsyncMock())
        monkeypatch.setattr(tenants, "ensure_calendar_tokens", AsyncMock())
        monkeypatch.setattr(voice_records, "purge_expired", AsyncMock())
        monkeypatch.setattr(outbox, "run_forever", make_worker("outbox"))
        monkeypatch.setattr(sla, "run_forever", make_worker("sla"))
        monkeypatch.setattr(sales, "run_forever", make_worker("sales"))
        monkeypatch.setattr(missed_calls, "run_forever", make_worker("missed_calls"))
        monkeypatch.setattr(call_insights, "run_forever", make_worker("call_insights"))
        monkeypatch.setattr(email_secretary, "run_forever", make_worker("email_secretary"))
        monkeypatch.setattr(calendar_connection, "run_forever", make_worker("calendar"))

        before_tasks = set(asyncio.all_tasks())
        async with main.lifespan(main.app):
            # Give every spawned worker a chance to start and enter stop.wait().
            for _ in range(20):
                if started == set(worker_names):
                    break
                await asyncio.sleep(0.005)
            assert started == set(worker_names), f"missing started workers: {set(worker_names) - started}"

        leaked = [t for t in asyncio.all_tasks() - before_tasks if not t.done()]
        assert not leaked, f"background tasks leaked after lifespan exit: {leaked}"
        assert events[-1] == "db:close", f"expected db:close last, got {events}"
        for name in worker_names:
            assert f"stopped:{name}" in events, f"{name} worker was not awaited before shutdown completed"

    asyncio.run(scenario())


def test_lifespan_still_awaits_remaining_workers_and_closes_db_when_one_worker_errors(monkeypatch):
    async def scenario():
        events: list[str] = []

        async def _boom(stop: asyncio.Event):
            await stop.wait()
            raise RuntimeError("simulated worker crash during shutdown")

        def make_worker(name: str):
            async def _run(stop: asyncio.Event):
                await stop.wait()
                await asyncio.sleep(0.01)
                events.append(f"stopped:{name}")

            return _run

        async def _fake_close():
            events.append("db:close")

        monkeypatch.setattr(main.settings, "outbox_enabled", True)
        monkeypatch.setattr(db, "init", AsyncMock())
        monkeypatch.setattr(db, "close", _fake_close)
        monkeypatch.setattr(tenants, "ensure_report_tokens", AsyncMock())
        monkeypatch.setattr(tenants, "ensure_calendar_tokens", AsyncMock())
        monkeypatch.setattr(voice_records, "purge_expired", AsyncMock())
        monkeypatch.setattr(outbox, "run_forever", _boom)
        monkeypatch.setattr(sla, "run_forever", make_worker("sla"))
        monkeypatch.setattr(sales, "run_forever", make_worker("sales"))
        monkeypatch.setattr(missed_calls, "run_forever", make_worker("missed_calls"))
        monkeypatch.setattr(call_insights, "run_forever", make_worker("call_insights"))
        monkeypatch.setattr(email_secretary, "run_forever", make_worker("email_secretary"))
        monkeypatch.setattr(calendar_connection, "run_forever", make_worker("calendar"))

        async with main.lifespan(main.app):
            await asyncio.sleep(0.01)

        assert "stopped:missed_calls" in events
        assert "stopped:call_insights" in events
        assert events[-1] == "db:close"

    asyncio.run(scenario())


def test_uptime_workflow_does_not_probe_retired_crm_host():
    workflow = UPTIME_PATH.read_text()
    assert "crm.trendibizz.com" not in workflow, "retired crm.trendibizz.com probe is still in uptime.yml"
    for expected in (
        "https://trendibizz.com/",
        "https://chat.trendibizz.com/widget.js",
        "https://concierge.trendibizz.com/studio/",
        "https://concierge.trendibizz.com/owner-ui",
    ):
        assert expected in workflow, f"active endpoint {expected} missing from uptime.yml"
