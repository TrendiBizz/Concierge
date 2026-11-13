"""Where an address came from: caller ID, an email, an SMS, or typed in by the owner.

The owner's question was "if there is caller ID we should capture that automatically". These tests
pin the two halves of that: every channel tells the store which channel it was, and the bridged
phone path actually asks Asterisk who is calling instead of recording an empty number.
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app import asterisk_bridge, casetimeline, enquiries


def test_each_channel_names_itself_as_the_source(monkeypatch):
    seen = {}

    async def fake_reconcile(tenant_id, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(enquiries.casetimeline, "reconcile", fake_reconcile)
    for channel, extra in (("email", {"email": "hana@acme.co.nz"}),
                           ("sms", {"phone": "+6491234567"}),
                           ("phone", {"phone": "+6491234567"}),
                           ("chat", {})):
        seen.clear()
        with pytest.raises(RuntimeError):
            asyncio.run(enquiries.capture({"id": uuid.uuid4(), "slug": "acme"}, channel,
                                          "source-" + channel, "hello", **extra))
        assert seen.get("source") == channel, f"{channel} did not name itself as the source"


def _settings(host="pbx", user="concierge", secret="s"):
    return SimpleNamespace(ami_host=host, ami_port=5038, ami_user=user, ami_secret=secret)


def test_caller_id_is_read_from_asterisk(monkeypatch):
    async def channels(config):
        return [{"Channel": "PJSIP/0215551234-0001", "Uniqueid": "1752460000.42",
                 "CallerIDNum": "0215551234"}]

    monkeypatch.setattr(asterisk_bridge, "get_settings", lambda: _settings())
    monkeypatch.setattr(asterisk_bridge.asterisk_ami, "from_settings", lambda s: object())
    monkeypatch.setattr(asterisk_bridge.asterisk_ami, "channels", channels)
    found = asyncio.run(asterisk_bridge.caller_number("ast:1752460000.42"))
    assert found == "0215551234"


def test_an_unmatched_or_junk_number_is_not_attached(monkeypatch):
    async def channels(config):
        return [{"Channel": "PJSIP/0215551234-0001", "Uniqueid": "999.1", "CallerIDNum": "anonymous"}]

    monkeypatch.setattr(asterisk_bridge, "get_settings", lambda: _settings())
    monkeypatch.setattr(asterisk_bridge.asterisk_ami, "from_settings", lambda s: object())
    monkeypatch.setattr(asterisk_bridge.asterisk_ami, "channels", channels)
    assert asyncio.run(asterisk_bridge.caller_number("ast:1752460000.42")) == ""


def test_without_ami_settings_the_bridge_does_not_guess(monkeypatch):
    monkeypatch.setattr(asterisk_bridge, "get_settings", lambda: _settings(host=""))
    assert asyncio.run(asterisk_bridge.caller_number("ast:1752460000.42")) == ""
