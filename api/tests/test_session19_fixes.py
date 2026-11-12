"""Session 19: text-first wording, dedicated call number, automated-sender headers, failure reason."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import asterisk_bridge, cloudflare_inbound, live_calls


def _raw(*headers: str) -> bytes:
    return ("\r\n".join(headers) + "\r\n\r\nbody").encode()


# ---- automated-sender headers ---------------------------------------------------------------
def test_auto_submitted_from_another_system_is_automated():
    assert cloudflare_inbound.has_automated_headers(_raw("Auto-Submitted: auto-replied"))
    assert cloudflare_inbound.has_automated_headers(_raw("Auto-Submitted: auto-generated"))


def test_auto_submitted_no_is_a_person():
    assert not cloudflare_inbound.has_automated_headers(_raw("Auto-Submitted: no"))


def test_bulk_precedence_list_id_and_suppress_headers_are_automated():
    assert cloudflare_inbound.has_automated_headers(_raw("Precedence: bulk"))
    assert cloudflare_inbound.has_automated_headers(_raw("Precedence: Auto_Reply"))
    assert cloudflare_inbound.has_automated_headers(_raw("List-Id: <news.example.test>"))
    assert cloudflare_inbound.has_automated_headers(_raw("X-Auto-Response-Suppress: All"))


def test_ordinary_mail_and_missing_raw_are_not_automated():
    assert not cloudflare_inbound.has_automated_headers(_raw("From: a@example.test", "Subject: hi"))
    assert not cloudflare_inbound.has_automated_headers(None)
    assert not cloudflare_inbound.has_automated_headers(b"")


# ---- dedicated call number ------------------------------------------------------------------
def _pool(owner_number=None):
    row = {"owner_number": owner_number} if owner_number is not None else None
    return SimpleNamespace(fetchrow=AsyncMock(return_value=row))


def test_call_number_prefers_managed_then_dedicated_then_alert_number(monkeypatch):
    tenant = {"id": 1, "notify_phone": "+6421111111", "owner_call_phone": "+6422222222"}
    monkeypatch.setattr(live_calls.db, "pool", lambda: _pool("+6423333333"))
    assert asyncio.run(live_calls.owner_voice_number(tenant)) == "+6423333333"
    monkeypatch.setattr(live_calls.db, "pool", lambda: _pool())
    assert asyncio.run(live_calls.owner_voice_number(tenant)) == "+6422222222"
    tenant.pop("owner_call_phone")
    assert asyncio.run(live_calls.owner_voice_number(tenant)) == "+6421111111"


# ---- text-first wording ---------------------------------------------------------------------
def _take_over(monkeypatch, tenant):
    queue, task = AsyncMock(), AsyncMock()
    monkeypatch.setattr(live_calls.casetimeline, "reconcile", AsyncMock(return_value=None))
    monkeypatch.setattr(live_calls.owner_notifications, "queue", queue)
    monkeypatch.setattr(live_calls, "_turns", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_calls, "_callback_task", task)
    monkeypatch.setattr(live_calls, "_hang_up", AsyncMock(return_value=(False, "")))
    call = {"call_sid": "sip:abc", "from_number": "+6429999999", "session_id": "s1"}
    asyncio.run(live_calls.take_over(tenant, call))
    return queue.call_args.args[2], task.call_args.kwargs


def test_text_only_owner_is_told_to_reply_not_to_ring(monkeypatch):
    body, kwargs = _take_over(monkeypatch, {"id": 1, "slug": "t", "owner_text_only": True})
    assert "text or email" in body and "Ring them back" not in body
    assert kwargs["text_only"] is True


def test_ordinary_owner_still_hears_ring_them_back(monkeypatch):
    body, kwargs = _take_over(monkeypatch, {"id": 1, "slug": "t"})
    assert "Ring them back now." in body
    assert kwargs["text_only"] is False


# ---- failure reason -------------------------------------------------------------------------
def test_finish_accepts_a_failure_reason():
    import inspect
    params = inspect.signature(asterisk_bridge.finish).parameters
    assert "reason" in params and params["reason"].default == ""
