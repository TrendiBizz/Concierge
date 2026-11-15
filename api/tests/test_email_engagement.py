"""Email engagement: a click is recorded, an open is only ever labelled as a soft signal.

The pixel approach was rejected on 2026-11-15: Apple Mail Privacy Protection and Gmail's image
proxy fetch it whether or not the message is read, so it measures delivery infrastructure. These
tests pin the behaviour that replaced it — a stored destination per link, a deduped click, an
open recorded as an open, and no way to use the redirect as an open redirect.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import db, engagement
from app.main import app


def _pool(**kwargs):
    pool = SimpleNamespace(
        execute=AsyncMock(return_value=None), fetchval=AsyncMock(return_value=None),
        fetch=AsyncMock(return_value=[]), fetchrow=AsyncMock(return_value=None))
    for key, value in kwargs.items():
        setattr(pool, key, value)
    return pool


def test_a_provider_event_maps_only_for_engagement_events():
    assert engagement.provider_kind("opened") == "open"
    assert engagement.provider_kind("CLICK") == "click"
    assert engagement.provider_kind("delivered") == "delivered"
    assert engagement.provider_kind("hard_bounce") is None
    assert engagement.provider_kind("unsubscribed") is None
    assert engagement.provider_kind("") is None


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "ftp://example.com/x", "/relative/path",
    "https://user:pw@example.com/", "mailto:someone@example.com"])
def test_only_absolute_http_links_are_trackable(url):
    """The redirect target is read back from the database, so the only defence is refusing to
    store something that is not a plain http(s) URL in the first place."""
    assert engagement.clean_url(url) is None


def test_a_normal_link_is_accepted_unchanged():
    assert engagement.clean_url("https://concierge.trendibizz.com/studio#invite=abc") == \
        "https://concierge.trendibizz.com/studio#invite=abc"


def test_tracking_is_off_until_an_operator_sets_the_origin(monkeypatch):
    monkeypatch.setattr(engagement, "tracking_base", lambda: "")
    assert engagement.enabled_for("owner_alert") is False
    monkeypatch.setattr(engagement, "tracking_base", lambda: "https://concierge.trendibizz.com")
    assert engagement.enabled_for("owner_alert") is True
    # Customer-facing transactional mail stays plain: tracking it would rewrite a customer's links.
    assert engagement.enabled_for("quote_sent") is False


def test_render_html_escapes_the_body_and_rewrites_links(monkeypatch):
    monkeypatch.setattr(engagement, "tracking_base", lambda: "https://concierge.trendibizz.com")

    async def remember(outbox_id, tenant_id, url):
        return "tok123"

    monkeypatch.setattr(engagement, "remember_link", remember)
    html = asyncio.run(engagement.render_html(
        7, uuid.uuid4(), "Sign in: https://example.com/studio\n<script>alert(1)</script>"))
    assert '<a href="https://concierge.trendibizz.com/l/tok123">https://example.com/studio</a>' in html
    assert "&lt;script&gt;" in html and "<script>" not in html


def test_trailing_punctuation_stays_outside_the_link(monkeypatch):
    monkeypatch.setattr(engagement, "tracking_base", lambda: "https://x.test")

    async def remember(outbox_id, tenant_id, url):
        assert url == "https://example.com/a"  # the full stop is not part of the URL
        return "tok"

    monkeypatch.setattr(engagement, "remember_link", remember)
    html = asyncio.run(engagement.render_html(1, uuid.uuid4(), "See https://example.com/a."))
    assert "</a>." in html


def test_the_number_of_tracked_links_per_message_is_capped(monkeypatch):
    monkeypatch.setattr(engagement, "tracking_base", lambda: "https://x.test")
    calls = []

    async def remember(outbox_id, tenant_id, url):
        calls.append(url)
        return "t%d" % len(calls)

    monkeypatch.setattr(engagement, "remember_link", remember)
    text = " ".join(f"https://example.com/{i}" for i in range(engagement.MAX_LINKS_PER_MESSAGE + 5))
    asyncio.run(engagement.render_html(1, uuid.uuid4(), text))
    assert len(calls) == engagement.MAX_LINKS_PER_MESSAGE


def test_a_click_is_recorded_once_and_returns_its_destination(monkeypatch):
    tenant = uuid.uuid4()
    pool = _pool(fetchrow=AsyncMock(return_value={
        "token": "tok", "outbox_id": 3, "tenant_id": tenant, "url": "https://example.com/x"}))
    monkeypatch.setattr(db, "pool", lambda: pool)
    clicked = asyncio.run(engagement.record_click("tok", "203.0.113.9", "UA/1"))
    assert clicked == "https://example.com/x"
    sql, *args = pool.execute.await_args.args
    assert "ON CONFLICT (token, kind) DO NOTHING" in sql, "a refresh must not double-count"
    assert args[2] == "tok" and args[4] == "203.0.113.9"


def test_an_unknown_token_records_nothing(monkeypatch):
    pool = _pool(fetchrow=AsyncMock(return_value=None))
    monkeypatch.setattr(db, "pool", lambda: pool)
    assert asyncio.run(engagement.record_click("nope")) is None
    pool.execute.assert_not_awaited()


def test_provider_open_event_is_stored_against_the_message(monkeypatch):
    tenant = uuid.uuid4()
    pool = _pool(fetchval=AsyncMock(return_value=12))
    monkeypatch.setattr(db, "pool", lambda: pool)
    result = asyncio.run(engagement.record_provider_event(
        {"event": "opened", "email": "someone@example.com", "message-id": "<m1@x>", "tenant_id": tenant}))
    assert result == {"recorded": "open"}
    sql, *args = pool.execute.await_args.args
    assert "ON CONFLICT DO NOTHING" in sql
    assert args[1] == 12 and args[2] == "open"


def test_a_bounce_event_is_left_to_the_suppression_path(monkeypatch):
    """Hard bounces must still reach suppressions: recording them here would silently stop the
    address being suppressed."""
    pool = _pool()
    monkeypatch.setattr(db, "pool", lambda: pool)
    assert asyncio.run(engagement.record_provider_event({"event": "hard_bounce", "tenant_id": uuid.uuid4()})) \
        == {"ignored": "not an engagement event"}
    pool.execute.assert_not_awaited()


def test_the_redirect_returns_the_stored_destination_and_cannot_be_redirected_elsewhere(monkeypatch):
    async def record(token, ip="", user_agent=""):
        assert token == "tok"
        return "https://example.com/landing"

    monkeypatch.setattr(engagement, "record_click", record)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
            return await c.get("/l/tok", follow_redirects=False)

    result = asyncio.run(run())
    assert result.status_code == 302
    assert result.headers["location"] == "https://example.com/landing"
    assert result.headers["cache-control"] == "no-store"


def test_an_unknown_link_is_a_404_not_a_redirect(monkeypatch):
    async def record(token, ip="", user_agent=""):
        return None

    async def resolve(token):
        return None

    monkeypatch.setattr(engagement, "record_click", record)
    monkeypatch.setattr(engagement, "resolve", resolve)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
            return await c.get("/l/missing", follow_redirects=False)

    assert asyncio.run(run()).status_code == 404


def test_the_mailer_sends_a_multipart_alternative_when_html_is_supplied(monkeypatch):
    """A tracked email needs an HTML part, and the plain-text part must stay: text-only clients and
    spam filters both expect it."""
    from app import mailer

    sent = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer, "get_settings", lambda: SimpleNamespace(
        email_configured=True, smtp_host="mail.test", smtp_port=587, smtp_security="starttls",
        smtp_user="u", smtp_password="p", smtp_from="office@test.example"))
    mailer._send_sync("to@example.com", "Subject", "plain body",
                      html="<html><body><a href='https://x.test/l/tok'>x</a></body></html>")
    msg = sent["msg"]
    assert msg.is_multipart()
    kinds = {part.get_content_type() for part in msg.walk()}
    assert {"text/plain", "text/html"} <= kinds, "both parts must exist"
    assert "multipart/alternative" in kinds
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    assert "https://x.test/l/tok" in html_part.get_content()


def test_a_plain_email_stays_plain(monkeypatch):
    from app import mailer

    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent["msg"] = msg

        def quit(self):
            pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer, "get_settings", lambda: SimpleNamespace(
        email_configured=True, smtp_host="mail.test", smtp_port=587, smtp_security="starttls",
        smtp_user="u", smtp_password="p", smtp_from="office@test.example"))
    mailer._send_sync("to@example.com", "Subject", "plain body")
    assert not sent["msg"].is_multipart()


@pytest.mark.parametrize("value", ["http://example.com", "https://example.com/track",
                                   "https://example.com?x=1", "ftp://example.com"])
def test_the_tracking_origin_must_be_a_bare_https_origin(value):
    from app.config import Settings
    with pytest.raises(Exception):
        Settings(tracked_links_base=value)


def test_the_tracking_origin_defaults_to_off():
    from app.config import Settings
    assert Settings(tracked_links_base="").tracked_links_base == ""


def test_brevo_engagement_events_never_reach_the_suppression_path(monkeypatch):
    """An 'opened' event reaching suppressions.record_event would be ignored there, but a
    mislabelled bounce reaching engagement would stop the address being suppressed. Both routes
    must be disjoint: this test pins the branch in the webhook handler."""
    from app import main as app_main
    from app import suppressions

    recorded, suppressed = [], []

    async def record_provider_event(event):
        recorded.append(event.get("event"))
        return {"recorded": "open"}

    async def record_event(event):
        suppressed.append(event.get("event"))
        return {"suppressed": False}

    monkeypatch.setattr(engagement, "record_provider_event", record_provider_event)
    monkeypatch.setattr(suppressions, "record_event", record_event)
    monkeypatch.setattr(app_main, "get_settings", lambda: SimpleNamespace(brevo_webhook_secret="s3cret"))

    payload = [{"event": "opened", "email": "someone@example.com", "message-id": "<m@x>",
                "tenant_id": str(uuid.uuid4())},
               {"event": "hard_bounce", "email": "dead@example.com", "message-id": "<m2@x>",
                "tenant_id": str(uuid.uuid4())}]

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
            return await c.post("/webhooks/brevo?token=s3cret", json=payload)

    assert asyncio.run(run()).status_code == 200
    assert recorded == ["opened"]
    assert suppressed == ["hard_bounce"]
