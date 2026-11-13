"""The phone connector's receipts: a late or repeated receipt must never jam it again (stuck 2026-11-11)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import device_sms

JOB = "11111111-1111-1111-1111-111111111111"
DEVICE = {"id": "d1", "tenant_id": "t1"}


def _receipt(status="sent", receipt="guid-1"):
    return device_sms.Receipt(job_id=JOB, status=status, receipt=receipt)


def _run(monkeypatch, fetchrow_results, body):
    pool = SimpleNamespace(fetchrow=AsyncMock(side_effect=fetchrow_results), execute=AsyncMock())
    monkeypatch.setattr(device_sms.db, "pool", lambda: pool)
    result = asyncio.run(device_sms.receipt(body, DEVICE))
    return result, pool


def _statements(pool):
    return [call.args[0] for call in pool.execute.call_args_list]


def test_a_receipt_for_a_claimed_job_is_applied_as_before(monkeypatch):
    result, pool = _run(monkeypatch, [{"outbox_id": 5}], _receipt())
    assert result == {"ok": True}
    assert any("UPDATE outbox" in s for s in _statements(pool))
    assert any("UPDATE sms_devices SET verified_at" in s for s in _statements(pool))


def test_a_sent_receipt_without_a_receipt_id_is_still_refused(monkeypatch):
    with pytest.raises(HTTPException) as caught:
        _run(monkeypatch, [], _receipt(receipt=""))
    assert caught.value.status_code == 422


def test_a_repeated_identical_receipt_is_acknowledged(monkeypatch):
    result, pool = _run(monkeypatch, [None, {"status": "sent", "receipt": "guid-1"}], _receipt())
    assert result == {"ok": True}
    pool.execute.assert_not_called()


def test_a_late_verified_result_for_an_uncertain_job_is_applied(monkeypatch):
    """The 2026-11-11 jam: the Mac sent and verified the text, but its receipt arrived after the 5 minute window."""
    result, pool = _run(monkeypatch,
                        [None, {"status": "uncertain", "receipt": ""}, {"outbox_id": 7}], _receipt())
    assert result == {"ok": True}
    statements = _statements(pool)
    assert any("UPDATE outbox" in s for s in statements)
    assert any("UPDATE sms_devices SET verified_at" in s for s in statements)


def test_a_late_failed_result_for_an_uncertain_job_is_recorded_as_failed(monkeypatch):
    result, pool = _run(monkeypatch,
                        [None, {"status": "uncertain", "receipt": ""}, {"outbox_id": None}],
                        _receipt(status="failed", receipt=""))
    assert result == {"ok": True}
    assert not any("sms_devices" in s for s in _statements(pool))


def test_a_job_the_server_cancelled_is_acknowledged_without_changing_it(monkeypatch):
    result, pool = _run(monkeypatch, [None, {"status": "cancelled", "receipt": ""}], _receipt())
    assert result["ok"] is True and result["state"] == "cancelled"
    pool.execute.assert_not_called()


def test_an_unknown_job_is_acknowledged_so_the_connector_stops_retrying(monkeypatch):
    result, pool = _run(monkeypatch, [None, None], _receipt())
    assert result["ok"] is False and "Unknown" in result["note"]
    pool.execute.assert_not_called()


def test_an_uncertain_verdict_for_an_uncertain_job_is_just_acknowledged(monkeypatch):
    result, pool = _run(monkeypatch, [None, {"status": "uncertain", "receipt": ""}],
                        _receipt(status="uncertain", receipt=""))
    assert result == {"ok": True}
    pool.execute.assert_not_called()
