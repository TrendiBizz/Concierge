"""Phone prompt rules after the first real test call (2026-11-13)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import asterisk_bridge


def test_numbers_are_read_back_at_most_once_and_interruptions_are_not_restarted():
    rules = asterisk_bridge.READBACK_RULES
    assert "at most once" in rules
    assert "interrupts" in rules and "do not start the read-back over" in rules
    assert "override any tool instruction" in rules


def test_the_assistant_never_discusses_delivery_internals():
    assert "Never mention devices, queues" in asterisk_bridge.READBACK_RULES


def test_offline_rule_stops_text_offers():
    assert "Do not offer a text copy" in asterisk_bridge.SMS_OFFLINE_RULE
    assert "callback" in asterisk_bridge.SMS_OFFLINE_RULE


def test_sms_copy_available_follows_the_device(monkeypatch):
    pool = SimpleNamespace(fetchval=AsyncMock(return_value=1))
    monkeypatch.setattr(asterisk_bridge.db, "pool", lambda: pool)
    assert asyncio.run(asterisk_bridge.sms_copy_available("t1")) is True
    pool.fetchval = AsyncMock(return_value=None)
    assert asyncio.run(asterisk_bridge.sms_copy_available("t1")) is False


def test_a_failed_device_check_does_not_change_what_callers_hear(monkeypatch):
    pool = SimpleNamespace(fetchval=AsyncMock(side_effect=RuntimeError("db down")))
    monkeypatch.setattr(asterisk_bridge.db, "pool", lambda: pool)
    assert asyncio.run(asterisk_bridge.sms_copy_available("t1")) is True
