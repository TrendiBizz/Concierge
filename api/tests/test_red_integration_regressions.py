"""Regressions for the three integration suites broken by PR #27 (Owner alerts v2)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import config, hermes_ops, owner_issues


def test_settings_exposes_hermes_gateway_fields_and_route_stays_404_by_default():
    settings = config.Settings()
    assert settings.hermes_gateway_enabled is False
    assert settings.hermes_gateway_key == ""
    with pytest.raises(HTTPException) as exc:
        hermes_ops.require_gateway("")
    assert exc.value.status_code == 404


def test_sweep_unanswered_honours_tenant_min_score_and_marks_sla_alerted_at(monkeypatch):
    seen_probes: list[dict] = []
    executed_sql: list[tuple] = []

    class FakePool:
        async def fetch(self, sql, *args):
            return [
                {
                    "id": "t-explicit",
                    "name": "Explicit SLA Co",
                    "notify_email": "owner@explicit.test",
                    "timezone": "Pacific/Auckland",
                    "sla_minutes": 15,
                    "sla_min_score": 70,
                },
                {
                    "id": "t-default",
                    "name": "Default SLA Co",
                    "notify_email": "owner@default.test",
                    "timezone": "Pacific/Auckland",
                    "sla_minutes": 0,
                    "sla_min_score": 70,
                },
            ]

        async def fetchval(self, sql, *args):
            return 1

        async def execute(self, sql, *args):
            executed_sql.append((sql, args))
            return "UPDATE 1"

    async def fake_overdue(probe, max_age_days=2):
        seen_probes.append(probe)
        if probe["id"] == "t-explicit":
            return [{
                "id": "lead-hot",
                "name": "Hot Waiting",
                "phone": "+6421000001",
                "email": "",
                "channel": "chat",
                "minutes_waiting": 30,
            }]
        return []

    monkeypatch.setattr(owner_issues.db, "pool", lambda: FakePool())
    monkeypatch.setattr(owner_issues.sla, "overdue", fake_overdue)
    monkeypatch.setattr(owner_issues.outbox, "next_allowed_send", lambda tz, when: datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(owner_issues, "raise_issue", AsyncMock(return_value=True))

    raised = asyncio.run(owner_issues.sweep_unanswered())
    assert raised == 1

    by_id = {p["id"]: p for p in seen_probes}
    assert by_id["t-explicit"]["sla_minutes"] == 15
    assert by_id["t-explicit"]["sla_min_score"] == 70
    assert by_id["t-default"]["sla_minutes"] == config.get_settings().owner_issue_unanswered_minutes
    assert by_id["t-default"]["sla_min_score"] == 0

    assert any("UPDATE leads SET sla_alerted_at = now()" in sql and args == ("lead-hot",) for sql, args in executed_sql)
