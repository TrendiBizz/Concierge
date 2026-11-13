"""Web Push for owner alerts: safe destinations, short text, caps, clean-up, and it can never fail an alert."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import webpush


@pytest.fixture(autouse=True)
def _clean_state():
    webpush._hits.clear()
    webpush._seen.clear()
    yield
    webpush._hits.clear()
    webpush._seen.clear()


GOOD = [
    "https://fcm.googleapis.com/fcm/send/abc123",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://web.push.apple.com/QGxyz",
    "https://wns2-par02p.notify.windows.com/w/?token=x",
]
BAD = [
    "http://fcm.googleapis.com/fcm/send/abc",                 # not https
    "https://fcm.googleapis.com.evil.test/x",                 # look-alike suffix
    "https://evil.test/fcm.googleapis.com",                   # host is evil.test
    "https://fcm.googleapis.com@evil.test/x",                 # credentials trick
    "https://user:pw@fcm.googleapis.com/x",                   # credentials
    "https://127.0.0.1/x", "https://localhost/x", "https://[::1]/x", "https://10.0.0.5/x",
    "https://fcm.googleapis.com:6379/x",                      # odd port
    "ftp://fcm.googleapis.com/x", "", "not a url",
]


@pytest.mark.parametrize("url", GOOD)
def test_real_push_services_are_accepted(url):
    assert webpush.allowed_endpoint(url)


@pytest.mark.parametrize("url", BAD)
def test_anything_else_is_refused_so_the_server_cannot_be_aimed_inside(url):
    assert not webpush.allowed_endpoint(url)


def test_payload_is_short_and_has_no_links():
    body = "Take over now: +6421 123 456\n" + "x" * 400 + " https://secret.test/recordings/shared/TOKEN"
    data = json.loads(webpush.make_payload("  Phone   message for Trendi  ", body, "k"))
    assert data["title"] == "Phone message for Trendi"
    assert len(data["body"]) <= 140 and data["body"].endswith("...")
    assert "http" not in data["body"] and "TOKEN" not in json.dumps(data)
    assert data["url"] == "/owner-ui" and len(data["tag"]) == 16


def test_empty_subject_still_has_a_title():
    assert json.loads(webpush.make_payload("", "hello"))["title"] == "New alert"


def test_same_alert_is_pushed_once_and_the_hourly_cap_holds():
    assert webpush._allow("t1", "alert-1", now=1000.0)
    assert not webpush._allow("t1", "alert-1", now=1100.0)              # duplicate within 10 minutes
    assert webpush._allow("t1", "alert-1", now=1000.0 + 700)             # fine after the window
    webpush._hits.clear(); webpush._seen.clear()
    for i in range(webpush.HOURLY_CAP):
        assert webpush._allow("t2", f"k{i}", now=2000.0 + i)
    assert not webpush._allow("t2", "one-more", now=2100.0)
    assert webpush._allow("t2", "one-more", now=2000.0 + 3700)
    assert webpush._allow("other-business", "k0", now=2100.0)            # caps are per business


def _settings(on=True):
    return SimpleNamespace(vapid_private_key="priv" if on else "", vapid_public_key="pub" if on else "",
                           vapid_subject="mailto:admin@example.test")


def test_nothing_is_sent_when_not_configured(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings(False))
    assert asyncio.run(webpush.notify({"id": 1}, "s", "b", "d")) == 0


def test_notify_sends_to_each_device_and_cleans_up(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings())
    rows = [{"id": 1, "endpoint": "e-ok", "p256dh": "p", "auth": "a"},
            {"id": 2, "endpoint": "e-gone", "p256dh": "p", "auth": "a"},
            {"id": 3, "endpoint": "e-bad", "p256dh": "p", "auth": "a"}]
    pool = SimpleNamespace(fetch=AsyncMock(return_value=rows), execute=AsyncMock())
    monkeypatch.setattr(webpush.db, "pool", lambda: pool)
    outcomes = {"e-ok": "ok", "e-gone": "gone", "e-bad": "error"}
    monkeypatch.setattr(webpush, "_send_blocking", lambda endpoint, p, a, d: outcomes[endpoint])
    assert asyncio.run(webpush.notify({"id": 9}, "Subject", "Body", "dedupe-1")) == 1
    statements = [call.args[0] for call in pool.execute.call_args_list]
    assert any("last_ok_at=now()" in s for s in statements)
    assert any(s.startswith("DELETE FROM push_subscriptions WHERE id=$1") for s in statements)
    assert any("failures=failures+1" in s for s in statements)


def test_a_database_failure_never_breaks_the_alert(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings())
    pool = SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("down")), execute=AsyncMock())
    monkeypatch.setattr(webpush.db, "pool", lambda: pool)
    assert asyncio.run(webpush.notify({"id": 9}, "s", "b", "d")) == 0


def test_a_missing_library_is_a_failure_not_a_crash(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings())
    import builtins
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "pywebpush":
            raise ImportError("no pywebpush")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert webpush._send_blocking("https://fcm.googleapis.com/x", "p", "a", "{}") == "error"


def test_test_push_says_so_when_the_device_is_not_subscribed(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings())
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value=None), execute=AsyncMock())
    monkeypatch.setattr(webpush.db, "pool", lambda: pool)
    result = asyncio.run(webpush.send_test(1, "https://fcm.googleapis.com/x"))
    assert result["sent"] == 0 and "not turned on" in result["note"]


def test_test_push_reports_not_set_up(monkeypatch):
    monkeypatch.setattr(webpush, "get_settings", lambda: _settings(False))
    assert asyncio.run(webpush.send_test(1, "e"))["sent"] == 0
