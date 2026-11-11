"""Route-level checks for the AI quote draft.

The draft must use only catalogue prices, never write to the database, and still
produce a usable draft when the model is unavailable (the takeoff fallback).
"""
import asyncio
from types import SimpleNamespace
from uuid import UUID

import fastapi
import pytest

from app import llm, quotations

TENANT = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
LEAD = UUID("11111111-1111-4111-8111-111111111111")
DESIGN = UUID("22222222-2222-4222-8222-222222222222")

CATALOG = [
    {"id": "p1", "name": "Wall cladding (installed)", "description": "", "unit": "m2", "sale_price_cents": 18500},
    {"id": "p2", "name": "Site visit", "description": "", "unit": "each", "sale_price_cents": 25000},
]


class FakePool:
    def __init__(self, design_summary=None):
        self.design_summary = design_summary
        self.statements = []

    async def fetch(self, sql, *args):
        self.statements.append(("fetch", sql, args))
        return CATALOG

    async def fetchrow(self, sql, *args):
        self.statements.append(("fetchrow", sql, args))
        if "FROM leads" in sql:
            return {"name": "Conrad", "email": "conrad@example.com", "phone": "", "channel": "email",
                    "message": "We need the workshop clad."}
        if "FROM design_uploads" in sql:
            return {"filename": "workshop.ifc", "summary": self.design_summary}
        return None


def wire(monkeypatch, pool):
    monkeypatch.setattr(quotations.db, "pool", lambda: pool)
    monkeypatch.setattr(quotations.owner_auth, "require_role", lambda *a, **k: None)


def user():
    return {"tenant_id": TENANT, "role": "owner", "tenant_name": "Pukeko Construction"}


def test_draft_uses_model_lines_and_never_writes(monkeypatch):
    pool = FakePool()
    wire(monkeypatch, pool)

    async def fake_complete(messages, **kwargs):
        assert "Site visit" in messages[1]["content"]  # catalogue prices are in the user turn
        return SimpleNamespace(content='```json\n{"title": "Workshop cladding", "notes": "Excludes scaffold.", "lines": '
                                       '[{"description": "Wall cladding (installed)", "quantity": 42, "unit_price_cents": 18500}]}\n```')

    monkeypatch.setattr(llm, "complete", fake_complete)
    result = asyncio.run(quotations.draft_quotation(quotations.DraftRequest(lead_id=LEAD, brief="clad the shed"), user=user()))
    assert result["source"] == "model"
    assert result["title"] == "Workshop cladding"
    assert result["notes"] == "Excludes scaffold."
    assert result["lines"][0]["amount_cents"] == 777000
    assert result["total_cents"] == 777000
    assert result["saved"] is False
    assert not [s for s in pool.statements if s[0] in ("execute",)] and all(
        "INSERT" not in s[1].upper() and "UPDATE" not in s[1].upper() for s in pool.statements)


def test_model_failure_falls_back_to_measured_takeoff(monkeypatch):
    pool = FakePool(design_summary={"net_cladding_area_m2": 10.0, "net_wall_area_m2": 14.0})
    wire(monkeypatch, pool)

    async def boom(messages, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(llm, "complete", boom)
    result = asyncio.run(quotations.draft_quotation(quotations.DraftRequest(design_id=DESIGN), user=user()))
    assert result["source"] == "measured"
    assert result["warnings"]
    assert result["lines"][0]["quantity"] == "10"
    assert result["lines"][0]["unit_price_cents"] == 18500


def test_model_output_without_catalogue_items_cannot_invent_prices(monkeypatch):
    pool = FakePool()
    wire(monkeypatch, pool)

    async def invent(messages, **kwargs):
        return SimpleNamespace(content='{"title": "Guess", "lines": [{"description": "Mystery item", '
                                       '"quantity": 1, "unit_price_cents": 999999}]}')

    monkeypatch.setattr(llm, "complete", invent)
    result = asyncio.run(quotations.draft_quotation(quotations.DraftRequest(brief="quote it"), user=user()))
    assert result["lines"][0]["product_id"] is None
    assert result["lines"][0]["unit_price_cents"] == 999999  # kept but unknown to the catalogue
    assert "price to confirm" not in result["notes"].lower()  # the server does not edit the model's wording


def test_design_without_takeoff_is_refused(monkeypatch):
    pool = FakePool(design_summary=None)
    wire(monkeypatch, pool)
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(quotations.draft_quotation(quotations.DraftRequest(design_id=DESIGN), user=user()))
    assert exc.value.status_code == 409


def test_empty_request_is_refused(monkeypatch):
    wire(monkeypatch, FakePool())
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(quotations.draft_quotation(quotations.DraftRequest(), user=user()))
    assert exc.value.status_code == 422
