"""The owner sales board: the pipeline route and adding an offline opportunity.

The board is not a second pipeline — it calls the same `sales.pipeline()` the admin dashboard and
the weekly summary use, so the three can never disagree about what is open or what it is worth.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from app import db, owner_auth, tenants
from app.main import app


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def test_pipeline_groups_by_stage_and_weights_the_forecast(monkeypatch):
    tenant_id = uuid.uuid4()
    tenant = {"id": tenant_id, "slug": "acme", "lead_value_cents": 2000}
    monkeypatch.setattr(tenants, "get_by_slug", AsyncMock(return_value=tenant))
    rows = [
        {"id": uuid.uuid4(), "name": "A", "status": "new", "value_cents": 10000},
        {"id": uuid.uuid4(), "name": "B", "status": "new", "value_cents": 0},
        {"id": uuid.uuid4(), "name": "C", "status": "won", "value_cents": 5000},
    ]
    pool = SimpleNamespace(fetch=AsyncMock(return_value=rows))
    monkeypatch.setattr(db, "pool", lambda: pool)

    async def auth():
        return {"tenant_id": tenant_id, "slug": "acme", "role": "owner"}

    app.dependency_overrides[owner_auth.current_user] = auth
    async def run():
        async with _client() as client:
            return await client.get("/owner/crm/pipeline")
    try:
        result = asyncio.run(run())
        assert result.status_code == 200
        body = result.json()
        assert body["stages"]["new"]["count"] == 2
        # The lead without its own value uses the client's average (2000), so the column is 12000.
        assert body["stages"]["new"]["value_cents"] == 12000
        assert body["stages"]["won"]["count"] == 1
        assert body["stages"]["won"]["value_cents"] == 5000
        assert body["open_value_cents"] == 12000
        assert body["won_value_cents"] == 5000
        assert body["weighted_value_cents"] == 1200  # 12000 * the 10% "new" odds
        assert body["average_lead_value_cents"] == 2000
    finally:
        app.dependency_overrides.clear()


def test_create_opportunity_inserts_into_the_owner_tenant(monkeypatch):
    tenant_id = uuid.uuid4()
    inserted = {"id": uuid.uuid4(), "tenant_id": tenant_id, "name": "Walk-in",
                "channel": "manual", "status": "new"}
    fetchrow = AsyncMock(return_value=inserted)
    monkeypatch.setattr(db, "pool", lambda: SimpleNamespace(fetchrow=fetchrow))

    async def auth():
        return {"tenant_id": tenant_id, "slug": "acme", "role": "owner"}

    app.dependency_overrides[owner_auth.current_user] = auth
    async def run(body):
        async with _client() as client:
            return await client.post("/owner/crm/leads", json=body)
    try:
        result = asyncio.run(run({"name": "Walk-in", "company": "Acme", "value_cents": 5000}))
        assert result.status_code == 201
        assert result.json()["id"] == str(inserted["id"])
        args = fetchrow.await_args.args
        assert args[1] == tenant_id
        assert args[2] == "Walk-in"
        assert args[3] == "Acme"
        assert args[7] == 5000
        assert "'manual'" in args[0] and "'new'" in args[0]

        fetchrow.reset_mock()
        assert asyncio.run(run({})).status_code == 422
        fetchrow.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_pipeline_requires_a_known_tenant(monkeypatch):
    monkeypatch.setattr(tenants, "get_by_slug", AsyncMock(return_value=None))

    async def auth():
        return {"tenant_id": uuid.uuid4(), "slug": "nobody", "role": "owner"}

    app.dependency_overrides[owner_auth.current_user] = auth
    async def run():
        async with _client() as client:
            return await client.get("/owner/crm/pipeline")
    try:
        assert asyncio.run(run()).status_code == 404
    finally:
        app.dependency_overrides.clear()
